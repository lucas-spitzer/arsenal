from __future__ import annotations

import pytest

from app.config import get_settings
from app.llm_defaults import (
    GEMINI_NANO_BANANA_21_MODEL,
    GROK_IMAGINE_IMAGE_2_MODEL,
    OPENAI_IMAGE_FLARE_MODEL,
    OPENAI_IMAGE_SUNBURST_MODEL,
)
from app.mathesys.study_material.images import resolve_image_settings
from app.services.api_pricing import XAI_IMAGE_1K_MEDIUM_PRICE
from app.services.images.catalog import (
    NANO_BANANA_21_1K_PRICE,
    IMAGE_MODEL_CATALOG,
    OPENAI_IMAGE_HIGH_1024_PRICE,
    ImageStageDefault,
    image_default_from_rows,
    validate_image_selection,
)
from app.services.stage_run_billing import image_stage_run_completion_fields


def test_image_catalog_lists_design_defaults() -> None:
    by_model = {entry.model: entry for entry in IMAGE_MODEL_CATALOG}

    assert set(by_model) == {
        OPENAI_IMAGE_SUNBURST_MODEL,
        GEMINI_NANO_BANANA_21_MODEL,
        GROK_IMAGINE_IMAGE_2_MODEL,
    }
    assert by_model[GEMINI_NANO_BANANA_21_MODEL].capability_tier == 4
    assert by_model[OPENAI_IMAGE_SUNBURST_MODEL].capability_tier == 2
    assert by_model[GROK_IMAGINE_IMAGE_2_MODEL].capability_tier == 3
    assert by_model[OPENAI_IMAGE_SUNBURST_MODEL].price_per_image == OPENAI_IMAGE_HIGH_1024_PRICE
    assert by_model[GEMINI_NANO_BANANA_21_MODEL].price_per_image == NANO_BANANA_21_1K_PRICE
    assert by_model[GEMINI_NANO_BANANA_21_MODEL].display_name == "Nano Banana 2.1"
    assert by_model[GROK_IMAGINE_IMAGE_2_MODEL].price_per_image == XAI_IMAGE_1K_MEDIUM_PRICE
    assert by_model[OPENAI_IMAGE_SUNBURST_MODEL].provider == "openai"
    assert by_model[GEMINI_NANO_BANANA_21_MODEL].provider == "google"
    assert by_model[GROK_IMAGINE_IMAGE_2_MODEL].provider == "xai"


def test_validate_image_selection_rejects_unknown_and_mismatched_provider() -> None:
    assert validate_image_selection("openai", OPENAI_IMAGE_SUNBURST_MODEL) is None
    assert validate_image_selection("openai", OPENAI_IMAGE_FLARE_MODEL) is not None
    assert validate_image_selection("openai", "gpt-image-2") is not None
    assert validate_image_selection("openai", GEMINI_NANO_BANANA_21_MODEL) is not None
    assert validate_image_selection("xai", OPENAI_IMAGE_SUNBURST_MODEL) is not None
    assert validate_image_selection("xai", GROK_IMAGINE_IMAGE_2_MODEL) is None


def test_image_default_from_rows_ignores_other_actions() -> None:
    assert image_default_from_rows([
        {"stage_action": "audio_narration", "provider": "google", "model": "gemini-3.8-flash-tts"},
    ]) is None
    assert image_default_from_rows([
        {
            "stage_action": "study_material_image",
            "provider": "openai",
            "model": OPENAI_IMAGE_SUNBURST_MODEL,
        },
    ]) == ImageStageDefault(
        provider="openai",
        model=OPENAI_IMAGE_SUNBURST_MODEL,
        quality="high",
    )
    assert image_default_from_rows([
        {
            "stage_action": "study_material_image",
            "provider": "google",
            "model": GEMINI_NANO_BANANA_21_MODEL,
            "image_quality": "high",
        },
    ]) == ImageStageDefault(
        provider="google",
        model=GEMINI_NANO_BANANA_21_MODEL,
        quality="high",
    )
    assert image_default_from_rows([
        {
            "stage_action": "study_material_image",
            "provider": "xai",
            "model": GROK_IMAGINE_IMAGE_2_MODEL,
        },
    ]) == ImageStageDefault(
        provider="xai",
        model=GROK_IMAGINE_IMAGE_2_MODEL,
        quality="medium",
    )


def _pin_env_image_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDY_MATERIAL_IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("STUDY_MATERIAL_OPENAI_IMAGE_MODEL", OPENAI_IMAGE_FLARE_MODEL)
    monkeypatch.setenv("STUDY_MATERIAL_GOOGLE_IMAGE_MODEL", GEMINI_NANO_BANANA_21_MODEL)
    get_settings.cache_clear()


def test_resolve_image_settings_uses_workspace_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        None,
        default_provider="google",
        default_model=GEMINI_NANO_BANANA_21_MODEL,
    )

    assert resolved["provider"] == "google"
    assert resolved["model"] == GEMINI_NANO_BANANA_21_MODEL
    get_settings.cache_clear()


def test_resolve_image_settings_keeps_explicit_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {"provider": "openai", "model": OPENAI_IMAGE_SUNBURST_MODEL, "quality": "low"},
        default_provider="google",
        default_model=GEMINI_NANO_BANANA_21_MODEL,
    )

    assert resolved["provider"] == "openai"
    assert resolved["model"] == OPENAI_IMAGE_SUNBURST_MODEL
    assert resolved["quality"] == "low"
    get_settings.cache_clear()


def test_resolve_image_settings_keeps_provider_when_workspace_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {"provider": "openai"},
        default_provider="google",
        default_model=GEMINI_NANO_BANANA_21_MODEL,
    )

    assert resolved["provider"] == "openai"
    assert resolved["model"] == OPENAI_IMAGE_FLARE_MODEL
    get_settings.cache_clear()


def test_resolve_image_settings_uses_workspace_model_for_same_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {"provider": "openai"},
        default_provider="openai",
        default_model=OPENAI_IMAGE_SUNBURST_MODEL,
    )

    assert resolved["model"] == OPENAI_IMAGE_SUNBURST_MODEL
    get_settings.cache_clear()


def test_resolve_image_settings_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings({})

    assert resolved["provider"] == "openai"
    assert resolved["model"] == OPENAI_IMAGE_FLARE_MODEL
    get_settings.cache_clear()
