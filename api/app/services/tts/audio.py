"""PCM helpers shared by Cartesia and Gemini TTS clients."""

from __future__ import annotations

import io
import logging
import wave

from app.services.tts.alignment import tokenize_with_spans
from app.services.tts.types import WordTiming

logger = logging.getLogger(__name__)

_SAMPLE_WIDTH = 2


def pcm_s16le_to_wav(
    pcm: bytes,
    *,
    sample_rate: int,
    channels: int = 1,
) -> bytes:
    """Wrap little-endian 16-bit PCM in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(_SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


def pcm_duration_seconds(
    pcm: bytes,
    *,
    sample_rate: int,
    channels: int = 1,
) -> float:
    frame_bytes = _SAMPLE_WIDTH * channels
    if frame_bytes <= 0 or not pcm or sample_rate <= 0:
        return 0.0
    return len(pcm) / (sample_rate * frame_bytes)


def sample_rate_from_mime(mime: str | None, *, default: int = 24000) -> int:
    if not mime:
        return default
    for part in mime.split(";"):
        token = part.strip().lower()
        if token.startswith("rate="):
            try:
                return int(token.split("=", 1)[1])
            except ValueError:
                return default
    return default


def even_word_timings(text: str, duration_seconds: float) -> list[WordTiming]:
    """Spread whitespace tokens evenly across the clip.

    Used when a provider does not return word alignments. Highlighting will
    track the token stream but will not match spoken pacing exactly.
    """
    tokens = tokenize_with_spans(text)
    if not tokens or duration_seconds <= 0:
        return [
            WordTiming(
                index=token.index,
                word=token.text,
                start=0.0,
                end=0.0,
                start_char=token.start_char,
                end_char=token.end_char,
            )
            for token in tokens
        ]

    slot = duration_seconds / len(tokens)
    return [
        WordTiming(
            index=token.index,
            word=token.text,
            start=token.index * slot,
            end=(token.index + 1) * slot,
            start_char=token.start_char,
            end_char=token.end_char,
        )
        for token in tokens
    ]
