"""Curated catalog of selectable narration TTS models and voices.

``price_per_million`` is the published list price in USD per million characters
(Starter / pay-as-you-go sticker rate). It feeds the Stage Models UI and is the
fallback for billing in app.services.api_pricing; an env override always wins.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.tts_defaults import (
    AUDIO_NARRATION_ACTION,
    DEFAULT_NARRATION_MODEL,
    tts_provider_for_model,
)

ELEVENLABS_DEFAULT_VOICE_ID = "4YYIPFl9wE5c4L2eu2Gb"
CARTESIA_DEFAULT_VOICE_ID = "4df027cb-2920-4a1f-8c34-f21529d5c3fe"
CARTESIA_JAMESON_VOICE_ID = "a5136bf9-224c-4d76-b823-52bd5efcffcc"
GEMINI_DEFAULT_VOICE_ID = "Sadaltager"
GEMINI_SADALTAGER_VOICE_ID = "Sadaltager"

# Speechify Starter / PAYG list: $10 / 1M characters.
# https://speechify.ai/pricing — Scale is $6/1M, Pro $8/1M.
SPEECHIFY_LIST_PRICE_PER_MILLION = 10.00

# ElevenLabs API list for Multilingual v2 / v3: $0.10 / 1K characters = $100 / 1M.
# https://elevenlabs.io/pricing/api
ELEVENLABS_V3_LIST_PRICE_PER_MILLION = 100.00

# Cartesia Sonic TTS is ~1 credit per character. Pro is $5 / 100K credits = $50 / 1M.
# https://docs.cartesia.ai/pricing — Scale is ~$37.38 ($299 / 8M credits).
CARTESIA_SONIC_LIST_PRICE_PER_MILLION = 50.00

# Gemini TTS has no per-character list price. Paid standard audio output is
# billed at 25 tokens/sec. At 750 chars/min that converts output to a
# per-character sticker (input tokens are a rounding error next to audio).
# Rates below are the introductory paid tier through 2026-12-31. On 2027-01-01
# both output prices double ($18 and $12 per 1M audio tokens), which would
# make these stickers $36 and $24.
# https://ai.google.dev/gemini-api/docs/pricing
# Flash: $9 / 1M audio tokens ≈ $0.0135/min → $18 / 1M characters.
GEMINI_38_FLASH_TTS_LIST_PRICE_PER_MILLION = 18.00
# Flash-Lite: $6 / 1M audio tokens ≈ $0.009/min → $12 / 1M characters.
GEMINI_38_FLASH_LITE_TTS_LIST_PRICE_PER_MILLION = 12.00

SIMBA_32_VOICES: tuple[tuple[str, str], ...] = (
    ("hugh_32", "Hugh"),
    ("beatrice_32", "Beatrice"),
    ("dominic_32", "Dominic"),
    ("edmund_32", "Edmund"),
    ("geffen_32", "Geffen"),
    ("harper_32", "Harper"),
    ("imogen_32", "Imogen"),
    ("wyatt_32", "Wyatt"),
)


@dataclass(frozen=True)
class TtsVoice:
    id: str
    display_name: str


@dataclass(frozen=True)
class TtsCatalogModel:
    model: str
    provider: str
    display_name: str
    default_voice_id: str
    voices: tuple[TtsVoice, ...]
    price_per_million: float | None = None
    capability_tier: int = 3


def _voices(*pairs: tuple[str, str]) -> tuple[TtsVoice, ...]:
    return tuple(TtsVoice(id=voice_id, display_name=name) for voice_id, name in pairs)


TTS_MODEL_CATALOG: tuple[TtsCatalogModel, ...] = (
    TtsCatalogModel(
        model="simba-3.2",
        provider="speechify",
        display_name="Simba 3.2",
        default_voice_id="hugh_32",
        voices=_voices(*SIMBA_32_VOICES),
        price_per_million=SPEECHIFY_LIST_PRICE_PER_MILLION,
        capability_tier=1,
    ),
    TtsCatalogModel(
        model="eleven_v3",
        provider="elevenlabs",
        display_name="Eleven v3",
        default_voice_id=ELEVENLABS_DEFAULT_VOICE_ID,
        voices=_voices((ELEVENLABS_DEFAULT_VOICE_ID, "Burt Reynolds")),
        price_per_million=ELEVENLABS_V3_LIST_PRICE_PER_MILLION,
        capability_tier=5,
    ),
    TtsCatalogModel(
        model="sonic-3.6",
        provider="cartesia",
        display_name="Sonic 3.6",
        default_voice_id=CARTESIA_DEFAULT_VOICE_ID,
        voices=_voices(
            (CARTESIA_DEFAULT_VOICE_ID, "Carson"),
            (CARTESIA_JAMESON_VOICE_ID, "Jameson"),
        ),
        price_per_million=CARTESIA_SONIC_LIST_PRICE_PER_MILLION,
        capability_tier=4,
    ),
    TtsCatalogModel(
        model="gemini-3.8-flash-tts",
        provider="google",
        display_name="Gemini 3.8 Flash TTS",
        default_voice_id=GEMINI_DEFAULT_VOICE_ID,
        voices=_voices(
            ("Kore", "Kore"),
            (GEMINI_SADALTAGER_VOICE_ID, "Sadaltager"),
        ),
        price_per_million=GEMINI_38_FLASH_TTS_LIST_PRICE_PER_MILLION,
        capability_tier=3,
    ),
    TtsCatalogModel(
        model="gemini-3.8-flash-lite-tts",
        provider="google",
        display_name="Gemini 3.8 Flash-Lite TTS",
        default_voice_id=GEMINI_DEFAULT_VOICE_ID,
        voices=_voices(
            ("Kore", "Kore"),
            (GEMINI_SADALTAGER_VOICE_ID, "Sadaltager"),
        ),
        price_per_million=GEMINI_38_FLASH_LITE_TTS_LIST_PRICE_PER_MILLION,
        capability_tier=2,
    ),
)

TTS_SELECTABLE_PROVIDERS: frozenset[str] = frozenset(
    {"speechify", "elevenlabs", "cartesia", "google"},
)

TTS_CATALOG_BY_MODEL: dict[str, TtsCatalogModel] = {
    entry.model: entry for entry in TTS_MODEL_CATALOG
}


def get_tts_catalog_model(model: str | None) -> TtsCatalogModel | None:
    normalized = (model or "").strip().lower()
    if not normalized:
        return None
    for entry in TTS_MODEL_CATALOG:
        if entry.model.lower() == normalized:
            return entry
    return None


def default_voice_for_model(model: str | None) -> str:
    entry = get_tts_catalog_model(model)
    if entry is not None:
        return entry.default_voice_id
    provider = tts_provider_for_model(model or DEFAULT_NARRATION_MODEL)
    if provider == "elevenlabs":
        return ELEVENLABS_DEFAULT_VOICE_ID
    if provider == "cartesia":
        return CARTESIA_DEFAULT_VOICE_ID
    if provider == "google":
        return GEMINI_DEFAULT_VOICE_ID
    return "hugh_32"


def tts_catalog_list_price(model: str | None) -> float | None:
    entry = get_tts_catalog_model(model)
    if entry is None:
        return None
    return entry.price_per_million


def validate_tts_selection(provider: str | None, model: str | None) -> str | None:
    normalized_provider = (provider or "").strip().lower()
    normalized_model = (model or "").strip()

    if normalized_provider not in TTS_SELECTABLE_PROVIDERS:
        return f"Unsupported TTS provider '{provider}'."

    if not normalized_model:
        return "Model is required."

    inferred = tts_provider_for_model(normalized_model)
    if inferred != normalized_provider:
        return (
            f"Model '{normalized_model}' belongs to provider '{inferred}', "
            f"not '{normalized_provider}'."
        )

    entry = get_tts_catalog_model(normalized_model)
    if entry is not None and entry.provider != normalized_provider:
        return (
            f"Model '{normalized_model}' belongs to provider '{entry.provider}', "
            f"not '{normalized_provider}'."
        )

    return None


__all__ = [
    "AUDIO_NARRATION_ACTION",
    "TTS_MODEL_CATALOG",
    "TTS_SELECTABLE_PROVIDERS",
    "TtsCatalogModel",
    "TtsVoice",
    "default_voice_for_model",
    "get_tts_catalog_model",
    "tts_catalog_list_price",
    "validate_tts_selection",
]
