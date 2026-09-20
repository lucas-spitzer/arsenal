"""Shared TTS defaults — kept outside app.services to avoid import cycles with config."""

DEFAULT_NARRATION_MODEL = "simba-3.2"
DEFAULT_NARRATION_VOICE_ID = "hugh_32"

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
