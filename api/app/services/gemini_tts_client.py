"""Gemini 3.1 Flash TTS via the existing Google Generative AI client.

Gemini does not return word alignments. Tokens from ``text.split()`` are
spread evenly across clip duration so the Reader still highlights.
"""

from __future__ import annotations

import base64
import logging
import time
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
from app.services.tts.types import NarrationResult

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


class GeminiTtsError(RuntimeError):
    pass


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
    raise GeminiTtsError("Gemini TTS response missing audio inline data.")


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
        self.max_retries = max_retries or narration.max_retries
        self.max_segment_chars = (
            max_segment_chars or narration.google_tts_max_segment_chars
        )
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
        for attempt in range(self.max_retries):
            try:
                response = genai_client.models.generate_content(
                    model=self.model_id,
                    contents=text,
                    config=config,
                )
                return self._parse(response, text)
            except Exception as exc:
                if isinstance(exc, GeminiTtsError) and "GEMINI_API_KEY" in str(exc):
                    raise
                last_error = str(exc)
                if not _is_retryable(exc) or attempt >= self.max_retries - 1:
                    if isinstance(exc, GeminiTtsError):
                        raise
                    raise GeminiTtsError(
                        f"Gemini TTS synthesis failed ({len(text)} chars): "
                        f"{last_error}",
                    ) from exc
                wait_seconds = _RETRY_BACKOFF_SECONDS * (2**attempt)
                logger.warning(
                    "Gemini TTS attempt %d/%d failed for %d chars (%s); "
                    "retrying in %ds",
                    attempt + 1,
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

    def _parse(self, response: Any, text: str) -> NarrationResult:
        pcm, mime = _inline_audio(response)
        sample_rate = sample_rate_from_mime(mime, default=_DEFAULT_SAMPLE_RATE)
        duration = pcm_duration_seconds(pcm, sample_rate=sample_rate)
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
            audio=pcm_s16le_to_wav(pcm, sample_rate=sample_rate),
            words=words,
            duration_seconds=duration,
            request_id=None,
            character_cost=len(text),
            alignment_source="estimated",
            alignment_quality=timing_quality(text, words, duration),
        )
