"""Shared TTS defaults — kept outside app.services to avoid import cycles with config."""

SIMBA_MODEL = "simba-3.2"
ELEVEN_V3_MODEL = "eleven_v3"
SONIC_MODEL = "sonic-3.6"
GEMINI_FLASH_TTS_MODEL = "gemini-3.8-flash-tts"
GEMINI_FLASH_LITE_TTS_MODEL = "gemini-3.8-flash-lite-tts"

DEFAULT_NARRATION_MODEL = GEMINI_FLASH_TTS_MODEL
DEFAULT_NARRATION_VOICE_ID = "Sadaltager"

# Same idea as MODEL_FAMILIES: .env names the family, code names the current id.
TTS_MODEL_FAMILIES: dict[str, str] = {
    "simba": SIMBA_MODEL,
    "eleven": ELEVEN_V3_MODEL,
    "sonic": SONIC_MODEL,
    "gemini-flash-tts": GEMINI_FLASH_TTS_MODEL,
    "gemini-flash-lite-tts": GEMINI_FLASH_LITE_TTS_MODEL,
}

SPEECHIFY_BATCH_MAX_CHARS = 2000
SPEECHIFY_STREAM_MAX_CHARS = 20_000
CARTESIA_MAX_SEGMENT_CHARS = 10_000
GOOGLE_TTS_MAX_SEGMENT_CHARS = 4_000

AUDIO_NARRATION_ACTION = "audio_narration"
AUDIO_NARRATION_LABEL = "Audio Narration"


def tts_provider_for_model(model_id: str) -> str:
    normalized = (model_id or "").strip().lower()
    if normalized.startswith("eleven"):
        return "elevenlabs"
    if normalized.startswith("sonic"):
        return "cartesia"
    if normalized.startswith("gemini"):
        return "google"
    return "speechify"
