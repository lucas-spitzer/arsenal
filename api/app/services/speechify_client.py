"""Speechify text-to-speech with word-level speech marks.

Batch ``POST /v1/audio/speech`` covers clips ≤ 2000 chars. Longer chapter
clips use ``POST /v1/audio/stream/with-timestamps`` (up to 20k chars). Both
return speech marks whose times are milliseconds; they are converted to seconds
to match the Reader's ``WordTiming`` contract.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import httpx

from app.config import get_settings
from app.services.tts.alignment import (
    RawTiming,
    align_offset_timings,
    align_ordered_timings,
    timing_quality,
)
from app.services.tts.types import NarrationResult, WordTiming
from app.tts_defaults import SPEECHIFY_BATCH_MAX_CHARS, SPEECHIFY_STREAM_MAX_CHARS

logger = logging.getLogger(__name__)

_API_BASE = "https://api.speechify.ai/v1/audio"
_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
_RETRY_BACKOFF_SECONDS = 5


class SpeechifyError(RuntimeError):
    pass


def words_from_speech_marks(
    marks: dict[str, Any] | list[dict[str, Any]] | None,
    text: str,
    *,
    duration_seconds: float | None = None,
) -> list[WordTiming]:
    """Map Speechify marks to source tokens using provider character offsets."""
    chunks: list[dict[str, Any]]
    if isinstance(marks, list):
        chunks = marks
    elif isinstance(marks, dict):
        raw = marks.get("chunks")
        chunks = raw if isinstance(raw, list) else []
    else:
        chunks = []

    raw_timings: list[RawTiming] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        value = str(chunk.get("value") or "").strip()
        if not value:
            continue
        start_ms = float(chunk.get("start_time") or 0)
        end_ms = float(chunk.get("end_time") or start_ms)
        start_char = chunk.get("start")
        end_char = chunk.get("end")
        raw_timings.append(
            RawTiming(
                value=value,
                start=start_ms / 1000.0,
                end=end_ms / 1000.0,
                start_char=int(start_char) if isinstance(start_char, (int, float)) else None,
                end_char=int(end_char) if isinstance(end_char, (int, float)) else None,
            )
        )

    duration = duration_seconds
    if duration is None:
        duration = max((mark.end for mark in raw_timings), default=0.0)
    if raw_timings and all(
        mark.start_char is not None and mark.end_char is not None
        for mark in raw_timings
    ):
        return align_offset_timings(text, raw_timings, duration)
    return align_ordered_timings(text, raw_timings, duration)


def _duration_seconds(
    words: list[WordTiming],
    marks: dict[str, Any] | None,
    audio_duration_ms: float | None,
) -> float:
    if audio_duration_ms is not None:
        return float(audio_duration_ms) / 1000.0
    if isinstance(marks, dict) and marks.get("end_time") is not None:
        return float(marks["end_time"]) / 1000.0
    if words:
        return words[-1].end
    return 0.0


class SpeechifyClient:
    provider = "speechify"
    audio_content_type = "audio/mpeg"

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
        self.api_key = api_key if api_key is not None else settings.speechify_api_key
        self.voice_id = voice_id or settings.voice_id
        self.model_id = model_id or settings.model_id
        self.request_timeout_seconds = (
            request_timeout_seconds or settings.request_timeout_seconds
        )
        self.max_retries = max_retries or settings.max_retries
        self.max_segment_chars = max_segment_chars or settings.speechify_max_segment_chars

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
            raise SpeechifyError("SPEECHIFY_API_KEY is not configured.")

        if len(text) > self.max_segment_chars:
            raise SpeechifyError(
                f"Segment is {len(text)} chars; Speechify max is {self.max_segment_chars}.",
            )

        body = {
            "input": text,
            "voice_id": self.voice_id,
            "model": self.model_id,
            "audio_format": "mp3",
        }

        if client is not None:
            return self._dispatch(client, body, text)

        with httpx.Client(timeout=self._timeout()) as owned:
            return self._dispatch(owned, body, text)

    def _dispatch(
        self,
        client: httpx.Client,
        body: dict[str, Any],
        text: str,
    ) -> NarrationResult:
        if len(text) <= SPEECHIFY_BATCH_MAX_CHARS:
            return self._post_batch(client, body, text)
        return self._post_stream(client, body, text)

    def _post_batch(
        self,
        client: httpx.Client,
        body: dict[str, Any],
        text: str,
    ) -> NarrationResult:
        last_error: str | None = None

        for attempt in range(self.max_retries):
            try:
                response = client.post(
                    f"{_API_BASE}/speech",
                    headers=self._headers(),
                    json=body,
                )
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                last_error = f"timeout: {exc}"
                if attempt >= self.max_retries - 1:
                    break
                self._backoff(attempt, last_error)
                continue

            if response.status_code < 400:
                return self._parse_batch(response, text)

            last_error = f"{response.status_code}: {response.text.strip()[:500]}"
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                break
            if attempt >= self.max_retries - 1:
                break
            self._backoff(attempt, last_error)

        raise SpeechifyError(
            f"Speechify synthesis failed after {self.max_retries} attempt(s): {last_error}",
        )

    def _parse_batch(self, response: httpx.Response, text: str) -> NarrationResult:
        payload = response.json()
        audio_b64 = payload.get("audio_data") or payload.get("audio")
        if not audio_b64:
            raise SpeechifyError("Speechify response missing audio_data.")
        audio = base64.b64decode(audio_b64)

        marks = payload.get("speech_marks")
        duration = _duration_seconds(
            [],
            marks if isinstance(marks, dict) else None,
            None,
        )
        words = words_from_speech_marks(
            marks if isinstance(marks, (dict, list)) else None,
            text,
            duration_seconds=duration,
        )
        character_cost = payload.get("billable_characters_count")
        try:
            cost = int(character_cost) if character_cost is not None else len(text)
        except (TypeError, ValueError):
            cost = len(text)

        return NarrationResult(
            audio=audio,
            words=words,
            duration_seconds=float(duration),
            request_id=response.headers.get("x-request-id") or response.headers.get("request-id"),
            character_cost=cost,
            alignment_source="provider",
            alignment_quality=timing_quality(text, words, float(duration)),
        )

    def _post_stream(
        self,
        client: httpx.Client,
        body: dict[str, Any],
        text: str,
    ) -> NarrationResult:
        last_error: str | None = None
        stream_body = {**body, "output_format": "mp3_24000_64"}

        for attempt in range(self.max_retries):
            try:
                with client.stream(
                    "POST",
                    f"{_API_BASE}/stream/with-timestamps",
                    headers=self._headers(),
                    json=stream_body,
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

        raise SpeechifyError(
            f"Speechify stream synthesis failed after {self.max_retries} attempt(s): "
            f"{last_error}",
        )

    def _parse_stream(self, response: httpx.Response, text: str) -> NarrationResult:
        audio_parts: list[bytes] = []
        mark_chunks: list[dict[str, Any]] = []
        audio_duration_ms: float | None = None
        character_cost = len(text)
        event_name = "message"
        data_lines: list[str] = []

        def flush() -> None:
            nonlocal audio_duration_ms, character_cost, event_name
            if not data_lines:
                event_name = "message"
                return
            raw = "\n".join(data_lines)
            data_lines.clear()
            name = event_name
            event_name = "message"
            if name in {"speech.chunk", "message"}:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    return
                if not isinstance(payload, dict):
                    return
                audio_b64 = payload.get("audio")
                if isinstance(audio_b64, str) and audio_b64:
                    audio_parts.append(base64.b64decode(audio_b64))
                marks = payload.get("speech_marks")
                if isinstance(marks, list):
                    mark_chunks.extend(
                        item for item in marks if isinstance(item, dict)
                    )
                elif isinstance(marks, dict):
                    nested = marks.get("chunks")
                    if isinstance(nested, list):
                        mark_chunks.extend(
                            item for item in nested if isinstance(item, dict)
                        )
            elif name == "speech.done":
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    return
                if isinstance(payload, dict):
                    if payload.get("audio_duration_ms") is not None:
                        audio_duration_ms = float(payload["audio_duration_ms"])
                    billed = payload.get("billable_characters_count")
                    try:
                        if billed is not None:
                            character_cost = int(billed)
                    except (TypeError, ValueError):
                        pass
            elif name == "speech.error":
                raise SpeechifyError(f"Speechify stream error: {raw[:500]}")

        for line in response.iter_lines():
            if line is None:
                continue
            if line == "":
                flush()
                continue
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip() or "message"
                continue
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
        flush()

        if not audio_parts:
            raise SpeechifyError("Speechify stream returned no audio.")

        duration = _duration_seconds([], None, audio_duration_ms)
        words = words_from_speech_marks(
            mark_chunks,
            text,
            duration_seconds=duration,
        )
        return NarrationResult(
            audio=b"".join(audio_parts),
            words=words,
            duration_seconds=duration,
            request_id=response.headers.get("x-request-id") or response.headers.get("request-id"),
            character_cost=character_cost,
            alignment_source="provider",
            alignment_quality=timing_quality(text, words, duration),
        )

    def _backoff(self, attempt: int, reason: str) -> None:
        wait_seconds = _RETRY_BACKOFF_SECONDS * (2**attempt)
        logger.warning(
            "Speechify synthesis attempt %d/%d failed (%s); retrying in %ds",
            attempt + 1,
            self.max_retries,
            reason,
            wait_seconds,
        )
        time.sleep(wait_seconds)


# Keep the stream cap visible to tests without importing config.
assert SPEECHIFY_STREAM_MAX_CHARS >= SPEECHIFY_BATCH_MAX_CHARS
