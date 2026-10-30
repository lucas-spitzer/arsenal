"""Gemini 3.8 Flash TTS via the existing Google Generative AI client.

Gemini does not return word alignments. Tokens from ``text.split()`` are
spread evenly across clip duration so the Reader still highlights.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
import wave
from datetime import UTC, datetime, timedelta
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.services.tts.alignment import timing_quality
from app.services.tts.audio import (
    even_word_timings,
    pcm_duration_seconds,
    pcm_s16le_to_wav,
    sample_rate_from_mime,
)
from app.services.tts.types import NarrationResult, TtsQuotaError

logger = logging.getLogger(__name__)

_DEFAULT_SAMPLE_RATE = 24000
_RETRY_BACKOFF_SECONDS = 5
# Preview TTS often returns a generic 400 INVALID_ARGUMENT or empty audio
# that succeeds on a later attempt. Google's docs also mention occasional
# 500s when the model emits text tokens instead of audio.
_RETRYABLE_MARKERS = (
    "429",
    "503",
    "UNAVAILABLE",
    "RESOURCE_EXHAUSTED",
    "INVALID_ARGUMENT",
    "INTERNAL",
    "missing audio inline data",
)
# A refusal (finish_reason OTHER) repeats for the same text, so retrying only
# spends the per-day request quota; the narration stage retries per paragraph.
_MAX_EMPTY_AUDIO_ATTEMPTS = 1
# Every retry counts against the daily quota, so a generic 400/500 flake gets
# one more try at most.
_FLAKE_MARKERS = ("INVALID_ARGUMENT", "INTERNAL")
_MAX_FLAKE_RETRIES = 1
_MAX_RATE_LIMIT_WAITS = 3
_RATE_LIMIT_PADDING_SECONDS = 2.0
_MAX_RATE_LIMIT_WAIT_SECONDS = 90.0
_RETRY_DELAY = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")
_RETRY_IN = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", re.IGNORECASE)


class GeminiTtsError(RuntimeError):
    pass


class GeminiQuotaError(GeminiTtsError, TtsQuotaError):
    """No more requests can be made today (Google's daily cap or our run budget)."""


def _is_rate_limited(message: str) -> bool:
    return "429" in message or "RESOURCE_EXHAUSTED" in message


def _is_daily_limit(message: str) -> bool:
    return "PerDay" in message or "per_day" in message


def _retry_after_seconds(message: str) -> float | None:
    match = _RETRY_DELAY.search(message)
    if match:
        return float(match.group(1))
    match = _RETRY_IN.search(message)
    if match and any(match.groups()):
        hours, minutes, seconds = (float(value or 0) for value in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    return None


def _inline_audio(response: Any) -> tuple[bytes, str]:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            mime = str(getattr(inline, "mime_type", None) or "")
            if isinstance(data, bytes) and data:
                return data, mime
            if isinstance(data, str) and data:
                return base64.b64decode(data), mime
    reasons = [
        str(getattr(candidate, "finish_reason", "") or "")
        for candidate in candidates
        if getattr(candidate, "finish_reason", None)
    ]
    detail = f" (finish_reason={', '.join(reasons)})" if reasons else ""
    raise GeminiTtsError(
        f"Gemini TTS response missing audio inline data{detail}."
    )


def _wav_duration_seconds(wav: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav), "rb") as wav_file:
            rate = wav_file.getframerate()
            if rate <= 0:
                return 0.0
            return wav_file.getnframes() / rate
    except wave.Error:
        return 0.0


def _as_wav(data: bytes, mime: str) -> tuple[bytes, float]:
    """Gemini 3.8 unary TTS returns WAV. Earlier models returned raw PCM."""
    if data.startswith(b"RIFF") or "wav" in mime.lower():
        return data, _wav_duration_seconds(data)
    sample_rate = sample_rate_from_mime(mime, default=_DEFAULT_SAMPLE_RATE)
    duration = pcm_duration_seconds(data, sample_rate=sample_rate)
    return pcm_s16le_to_wav(data, sample_rate=sample_rate), duration


def _is_retryable(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in _RETRYABLE_MARKERS)


class GeminiTtsClient:
    provider = "google"
    audio_content_type = "audio/wav"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        request_timeout_seconds: int | None = None,
        max_retries: int | None = None,
        max_segment_chars: int | None = None,
        min_request_interval_seconds: float | None = None,
        request_budget: int | None = None,
        client: Any = None,
    ) -> None:
        settings = get_settings()
        narration = settings.narration
        resolved_key = (
            api_key if api_key is not None else narration.google_api_key
        ) or settings.llm.google_api_key
        self.api_key = resolved_key
        self.voice_id = voice_id or narration.voice_id
        self.model_id = model_id or narration.model_id
        self.request_timeout_seconds = (
            request_timeout_seconds or narration.request_timeout_seconds
        )
        self.max_retries = max_retries or narration.google_tts_max_retries
        self.max_segment_chars = (
            max_segment_chars or narration.google_tts_max_segment_chars
        )
        self.min_request_interval_seconds = (
            narration.google_tts_min_request_interval_seconds
            if min_request_interval_seconds is None
            else min_request_interval_seconds
        )
        self.request_budget = (
            narration.google_tts_request_budget
            if request_budget is None
            else request_budget
        )
        self.requests_made = 0
        self._last_request_at: float | None = None
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _genai_client(self, injected: Any | None) -> Any:
        if injected is not None:
            return injected
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise GeminiTtsError("GEMINI_API_KEY is not configured.")
        return genai.Client(api_key=self.api_key)

    def synthesize_with_timestamps(
        self,
        text: str,
        *,
        previous_request_ids: list[str] | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
        client: Any = None,
    ) -> NarrationResult:
        del previous_request_ids, previous_text, next_text
        if not self.api_key and client is None and self._client is None:
            raise GeminiTtsError("GEMINI_API_KEY is not configured.")

        genai_client = self._genai_client(client)
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_id,
                    )
                )
            ),
        )

        last_error: str | None = None
        attempt = 0
        empty_audio_attempts = 0
        flake_attempts = 0
        rate_limit_waits = 0
        while attempt < self.max_retries:
            try:
                response = self._generate(genai_client, text, config)
                return self._parse(response, text)
            except GeminiQuotaError:
                raise
            except Exception as exc:
                if isinstance(exc, GeminiTtsError) and "GEMINI_API_KEY" in str(exc):
                    raise
                last_error = str(exc)
                if _is_rate_limited(last_error):
                    wait_seconds = self._rate_limit_wait(last_error, len(text), exc)
                    rate_limit_waits += 1
                    if rate_limit_waits > _MAX_RATE_LIMIT_WAITS:
                        raise GeminiQuotaError(
                            f"Gemini TTS per-minute limit kept failing ({len(text)} chars): "
                            f"{last_error}",
                            resume_at=datetime.now(UTC) + timedelta(seconds=wait_seconds),
                        ) from exc
                    logger.warning(
                        "Gemini TTS per-minute limit hit for %s; waiting %.0fs "
                        "(wait %d/%d)",
                        self.model_id,
                        wait_seconds,
                        rate_limit_waits,
                        _MAX_RATE_LIMIT_WAITS,
                    )
                    time.sleep(wait_seconds)
                    continue
                if "missing audio inline data" in last_error:
                    empty_audio_attempts += 1
                if any(marker in last_error for marker in _FLAKE_MARKERS):
                    flake_attempts += 1
                give_up = (
                    not _is_retryable(exc)
                    or attempt >= self.max_retries - 1
                    or empty_audio_attempts >= _MAX_EMPTY_AUDIO_ATTEMPTS
                    or flake_attempts > _MAX_FLAKE_RETRIES
                )
                if give_up:
                    if isinstance(exc, GeminiTtsError):
                        raise
                    raise GeminiTtsError(
                        f"Gemini TTS synthesis failed ({len(text)} chars): "
                        f"{last_error}",
                    ) from exc
                wait_seconds = _RETRY_BACKOFF_SECONDS * (2**attempt)
                attempt += 1
                logger.warning(
                    "Gemini TTS attempt %d/%d failed for %d chars (%s); "
                    "retrying in %ds",
                    attempt,
                    self.max_retries,
                    len(text),
                    last_error,
                    wait_seconds,
                )
                time.sleep(wait_seconds)

        raise GeminiTtsError(
            f"Gemini TTS synthesis failed after {self.max_retries} attempt(s) "
            f"({len(text)} chars): {last_error}",
        )

    def _generate(self, genai_client: Any, text: str, config: Any) -> Any:
        if self.request_budget > 0 and self.requests_made >= self.request_budget:
            raise GeminiQuotaError(
                f"Gemini TTS request budget reached ({self.request_budget} "
                f"requests this run for {self.model_id}).",
            )
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.min_request_interval_seconds:
                time.sleep(self.min_request_interval_seconds - elapsed)
        self._last_request_at = time.monotonic()
        self.requests_made += 1
        return genai_client.models.generate_content(
            model=self.model_id,
            contents=text,
            config=config,
        )

    def _rate_limit_wait(self, message: str, chars: int, exc: Exception) -> float:
        """Seconds to wait for a per-minute 429; raise for the per-day cap."""
        delay = _retry_after_seconds(message)
        if _is_daily_limit(message) or (
            delay is not None and delay > _MAX_RATE_LIMIT_WAIT_SECONDS
        ):
            resume_at = (
                datetime.now(UTC) + timedelta(seconds=delay)
                if delay is not None
                else None
            )
            raise GeminiQuotaError(
                f"Gemini TTS daily request limit reached for {self.model_id} "
                f"({chars} chars): {message}",
                resume_at=resume_at,
            ) from exc
        return (delay if delay is not None else 60.0) + _RATE_LIMIT_PADDING_SECONDS

    def _parse(self, response: Any, text: str) -> NarrationResult:
        audio_bytes, mime = _inline_audio(response)
        audio, duration = _as_wav(audio_bytes, mime)
        tokens = text.split()
        if tokens:
            logger.info(
                "Gemini TTS has no word alignments; spreading %d tokens evenly "
                "across %.2fs.",
                len(tokens),
                duration,
            )
        words = even_word_timings(text, duration)
        return NarrationResult(
            audio=audio,
            words=words,
            duration_seconds=duration,
            request_id=None,
            character_cost=len(text),
            alignment_source="estimated",
            alignment_quality=timing_quality(text, words, duration),
        )
