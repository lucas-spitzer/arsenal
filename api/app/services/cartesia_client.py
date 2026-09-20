"""Cartesia Sonic text-to-speech with word-level SSE timestamps.

POST /tts/sse returns raw PCM plus timestamp events. PCM is wrapped in WAV so
the Reader can play it without a local encoder. Word timings are seconds on
the clip timeline, matching the Speechify / ElevenLabs contract.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.config import get_settings
from app.services.tts.alignment import (
    RawTiming,
    align_ordered_timings,
    normalize_token,
    timing_quality,
)
from app.services.tts.audio import (
    pcm_duration_seconds,
    pcm_s16le_to_wav,
)
from app.services.tts.types import NarrationResult, WordTiming

logger = logging.getLogger(__name__)

_API_URL = "https://api.cartesia.ai/tts/sse"
_CARTESIA_VERSION = "2026-08-14"
_SAMPLE_RATE = 44100
_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
_RETRY_BACKOFF_SECONDS = 5


class CartesiaError(RuntimeError):
    pass


def words_from_cartesia_timestamps(
    timestamps: dict[str, Any] | None,
    text: str,
    *,
    duration_seconds: float,
) -> list[WordTiming]:
    """Map Cartesia timestamps onto source tokens with ordered text alignment."""
    expected = text.split()
    if not expected:
        return []

    if not isinstance(timestamps, dict):
        logger.warning(
            "Cartesia returned no word timestamps for %d tokens.",
            len(expected),
        )
        return []

    raw_words = timestamps.get("words") or []
    starts = timestamps.get("start") or []
    ends = timestamps.get("end") or []
    timings: list[RawTiming] = []
    for word, start, end in zip(raw_words, starts, ends, strict=False):
        value = str(word).strip()
        if not value:
            continue
        timings.append(RawTiming(value=value, start=float(start), end=float(end)))

    return align_ordered_timings(text, timings, duration_seconds)


class CartesiaClient:
    provider = "cartesia"
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
    ) -> None:
        settings = get_settings().narration
        self.api_key = api_key if api_key is not None else settings.cartesia_api_key
        self.voice_id = voice_id or settings.voice_id
        self.model_id = model_id or settings.model_id
        self.request_timeout_seconds = (
            request_timeout_seconds or settings.request_timeout_seconds
        )
        self.max_retries = max_retries or settings.max_retries
        self.max_segment_chars = max_segment_chars or settings.cartesia_max_segment_chars

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=30.0,
            read=float(self.request_timeout_seconds),
            write=30.0,
            pool=30.0,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Cartesia-Version": _CARTESIA_VERSION,
            "Content-Type": "application/json",
        }

    def synthesize_with_timestamps(
        self,
        text: str,
        *,
        previous_request_ids: list[str] | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
        client: httpx.Client | None = None,
    ) -> NarrationResult:
        del previous_request_ids, previous_text, next_text
        if not self.api_key:
            raise CartesiaError("CARTESIA_API_KEY is not configured.")

        body: dict[str, Any] = {
            "model_id": self.model_id,
            "transcript": text,
            "voice": {"id": self.voice_id},
            "locale": "en-US",
            "add_timestamps": True,
            "use_normalized_timestamps": False,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": _SAMPLE_RATE,
            },
        }

        if client is not None:
            return self._stream(client, body, text)
        with httpx.Client(timeout=self._timeout()) as owned:
            return self._stream(owned, body, text)

    def _stream(
        self,
        client: httpx.Client,
        body: dict[str, Any],
        text: str,
    ) -> NarrationResult:
        last_error: str | None = None

        for attempt in range(self.max_retries):
            try:
                with client.stream(
                    "POST",
                    _API_URL,
                    headers=self._headers(),
                    json=body,
                ) as response:
                    if response.status_code >= 400:
                        error_body = response.read().decode("utf-8", errors="replace")
                        last_error = f"{response.status_code}: {error_body.strip()[:500]}"
                        if response.status_code not in _RETRYABLE_STATUS_CODES:
                            break
                        if attempt >= self.max_retries - 1:
                            break
                        self._backoff(attempt, last_error)
                        continue
                    return self._parse_stream(response, text)
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                last_error = f"timeout: {exc}"
                if attempt >= self.max_retries - 1:
                    break
                self._backoff(attempt, last_error)
                continue

        raise CartesiaError(
            f"Cartesia synthesis failed after {self.max_retries} attempt(s): {last_error}",
        )

    def _parse_stream(self, response: httpx.Response, text: str) -> NarrationResult:
        pcm_parts: list[bytes] = []
        timestamp_events: list[dict[str, Any]] = []
        request_id = response.headers.get("x-request-id") or response.headers.get(
            "request-id",
        )
        data_lines: list[str] = []

        def flush() -> None:
            nonlocal request_id
            if not data_lines:
                return
            raw = "\n".join(data_lines)
            data_lines.clear()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return
            if not isinstance(payload, dict):
                return
            event_type = str(payload.get("type") or "")
            if event_type == "chunk":
                audio_b64 = payload.get("data")
                if isinstance(audio_b64, str) and audio_b64:
                    pcm_parts.append(base64.b64decode(audio_b64))
            elif event_type == "timestamps":
                word_ts = payload.get("word_timestamps")
                if isinstance(word_ts, dict):
                    timestamp_events.append(word_ts)
            elif event_type == "error":
                message = str(payload.get("message") or raw)[:500]
                raise CartesiaError(f"Cartesia stream error: {message}")
            echoed = payload.get("context_id")
            if isinstance(echoed, str) and echoed and not request_id:
                request_id = echoed

        for line in response.iter_lines():
            if line is None:
                continue
            if line == "":
                flush()
                continue
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
        flush()

        if not pcm_parts:
            raise CartesiaError("Cartesia stream returned no audio.")

        pcm = b"".join(pcm_parts)
        duration = pcm_duration_seconds(pcm, sample_rate=_SAMPLE_RATE)
        combined_words: list[str] = []
        combined_starts: list[float] = []
        combined_ends: list[float] = []
        seen: set[tuple[str, float, float]] = set()
        for event in timestamp_events:
            for word, start, end in zip(
                event.get("words") or [],
                event.get("start") or [],
                event.get("end") or [],
                strict=False,
            ):
                key = (str(word), float(start), float(end))
                if key in seen:
                    continue
                seen.add(key)
                combined_words.append(str(word))
                combined_starts.append(float(start))
                combined_ends.append(float(end))
        timestamps = {
            "words": combined_words,
            "start": combined_starts,
            "end": combined_ends,
        }
        words = words_from_cartesia_timestamps(
            timestamps,
            text,
            duration_seconds=duration,
        )
        source_values = [normalize_token(value) for value in text.split()]
        provider_values = [normalize_token(value) for value in combined_words]
        provider_match_ratio = SequenceMatcher(
            a=source_values,
            b=provider_values,
            autojunk=False,
        ).ratio()
        quality = timing_quality(text, words, duration)
        quality["provider_match_ratio"] = round(provider_match_ratio, 4)
        quality["valid"] = bool(quality["valid"] and provider_match_ratio >= 0.9)
        return NarrationResult(
            audio=pcm_s16le_to_wav(pcm, sample_rate=_SAMPLE_RATE),
            words=words,
            duration_seconds=duration,
            request_id=request_id,
            character_cost=len(text),
            alignment_source="provider",
            alignment_quality=quality,
        )

    def _backoff(self, attempt: int, reason: str) -> None:
        wait_seconds = _RETRY_BACKOFF_SECONDS * (2**attempt)
        logger.warning(
            "Cartesia synthesis attempt %d/%d failed (%s); retrying in %ds",
            attempt + 1,
            self.max_retries,
            reason,
            wait_seconds,
        )
        time.sleep(wait_seconds)
