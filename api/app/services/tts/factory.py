"""Build a TTS client for the generate-narration stage.

Resolution order: explicit args → workspace override → env defaults
(AUDIO_NARRATION_MODEL / AUDIO_NARRATION_VOICE_ID).
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import get_settings
from app.services.cartesia_client import CartesiaClient
from app.services.elevenlabs_client import ElevenLabsClient
from app.services.gemini_tts_client import GeminiTtsClient
from app.services.speechify_client import SpeechifyClient
from app.services.tts.catalog import TTS_SELECTABLE_PROVIDERS
from app.services.tts.types import NarrationResult
from app.tts_defaults import AUDIO_NARRATION_ACTION, tts_provider_for_model


class TtsClient(Protocol):
    provider: str
    voice_id: str
    model_id: str
    max_segment_chars: int
    audio_content_type: str

    @property
    def enabled(self) -> bool: ...

    def synthesize_with_timestamps(
        self,
        text: str,
        *,
        previous_request_ids: list[str] | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
        client: Any = None,
    ) -> NarrationResult: ...


@dataclass(frozen=True)
class NarrationOverride:
    provider: str
    model: str
    voice_id: str


_narration_override: contextvars.ContextVar[NarrationOverride | None] = contextvars.ContextVar(
    "workspace_narration_override",
    default=None,
)


def set_narration_override(
    override: NarrationOverride | None,
) -> contextvars.Token[NarrationOverride | None]:
    return _narration_override.set(override)


def reset_narration_override(
    token: contextvars.Token[NarrationOverride | None],
) -> None:
    _narration_override.reset(token)


def narration_override_from_rows(
    rows: list[dict[str, object]],
) -> NarrationOverride | None:
    for row in rows:
        action = str(row.get("stage_action") or "").strip()
        if action != AUDIO_NARRATION_ACTION:
            continue
        provider = str(row.get("provider") or "").strip().lower()
        model = str(row.get("model") or "").strip()
        voice_id = str(row.get("voice_id") or "").strip()
        if provider not in TTS_SELECTABLE_PROVIDERS or not model or not voice_id:
            return None
        return NarrationOverride(provider=provider, model=model, voice_id=voice_id)
    return None


def get_tts_client(
    *,
    model: str | None = None,
    voice_id: str | None = None,
) -> TtsClient:
    settings = get_settings().narration
    override = _narration_override.get()
    resolved_model = (
        (model or "").strip()
        or (override.model if override is not None else "")
        or settings.model_id
    )
    resolved_voice = (
        (voice_id or "").strip()
        or (override.voice_id if override is not None else "")
        or settings.voice_id
    )
    provider = tts_provider_for_model(resolved_model)

    if provider == "elevenlabs":
        return ElevenLabsClient(model_id=resolved_model, voice_id=resolved_voice)
    if provider == "cartesia":
        return CartesiaClient(model_id=resolved_model, voice_id=resolved_voice)
    if provider == "google":
        return GeminiTtsClient(model_id=resolved_model, voice_id=resolved_voice)
    return SpeechifyClient(model_id=resolved_model, voice_id=resolved_voice)
