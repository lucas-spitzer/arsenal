from app.services.tts.catalog import TTS_MODEL_CATALOG, validate_tts_selection

__all__ = [
    "TTS_MODEL_CATALOG",
    "get_tts_client",
    "narration_override_from_rows",
    "validate_tts_selection",
]


def __getattr__(name: str):
    # Factory imports the provider clients. Loading it from this package init
    # cycles back into ElevenLabs while that module is still defining them.
    if name in {"get_tts_client", "narration_override_from_rows"}:
        from app.services.tts import factory

        return getattr(factory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
