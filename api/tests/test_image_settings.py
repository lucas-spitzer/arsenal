from __future__ import annotations

import pytest

from app.config import get_settings
from app.llm_defaults import (
    GEMINI_3_PRO_IMAGE_MODEL,
    GEMINI_31_FLASH_IMAGE_MODEL,
    OPENAI_IMAGE_FLARE_MODEL,
    OPENAI_IMAGE_SUNBURST_MODEL,
)
from app.mathesys.study_material.images import (
    google_api_image_size,
    image_control_catalog,
    openai_pixel_size,
    resolve_image_settings,
)


def _pin_env_image_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDY_MATERIAL_IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("STUDY_MATERIAL_OPENAI_IMAGE_MODEL", OPENAI_IMAGE_SUNBURST_MODEL)
    monkeypatch.setenv("STUDY_MATERIAL_GOOGLE_IMAGE_MODEL", GEMINI_31_FLASH_IMAGE_MODEL)
    get_settings.cache_clear()


def test_resolve_keeps_openai_quality_and_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {
            "provider": "openai",
            "model": OPENAI_IMAGE_SUNBURST_MODEL,
            "quality": "xhigh",
            "resolution": "4K",
        },
    )

    assert resolved["quality"] == "xhigh"
    assert resolved["resolution"] == "4K"
    assert resolved["thinking_level"] is None
    get_settings.cache_clear()


def test_resolve_rejects_unknown_openai_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {"provider": "openai", "model": OPENAI_IMAGE_FLARE_MODEL, "quality": "ultra"},
    )

    assert resolved["quality"] == "high"
    assert resolved["resolution"] == "1K"
    get_settings.cache_clear()


def test_resolve_keeps_flash_half_k_and_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {
            "provider": "google",
            "model": GEMINI_31_FLASH_IMAGE_MODEL,
            "image_size": "0.5K",
            "thinking_level": "high",
        },
    )

    assert resolved["image_size"] == "0.5K"
    assert resolved["thinking_level"] == "high"
    get_settings.cache_clear()


def test_resolve_uses_workspace_quality_when_the_component_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_env_image_default(monkeypatch)

    openai = resolve_image_settings(
        None,
        default_provider="openai",
        default_model=OPENAI_IMAGE_SUNBURST_MODEL,
        default_quality="max",
    )
    kept = resolve_image_settings(
        {"quality": "low", "resolution": "4K"},
        default_provider="openai",
        default_model=OPENAI_IMAGE_SUNBURST_MODEL,
        default_quality="max",
    )
    google = resolve_image_settings(
        None,
        default_provider="google",
        default_model=GEMINI_31_FLASH_IMAGE_MODEL,
        default_quality="high",
    )

    assert openai["quality"] == "max"
    assert openai["resolution"] == "1K"
    assert kept["quality"] == "low"
    assert kept["resolution"] == "4K"
    assert google["thinking_level"] == "high"
    assert google["image_size"] == "2K"
    get_settings.cache_clear()


def test_resolve_drops_half_k_on_pro(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {
            "provider": "google",
            "model": GEMINI_3_PRO_IMAGE_MODEL,
            "image_size": "0.5K",
            "thinking_level": "high",
        },
    )

    assert resolved["image_size"] == "1K"
    assert resolved["thinking_level"] is None
    get_settings.cache_clear()


def test_google_half_k_is_sent_as_512() -> None:
    assert google_api_image_size("0.5K") == "512"
    assert google_api_image_size("2K") == "2K"


def test_openai_pixel_size_map() -> None:
    assert openai_pixel_size("1:1", "1K") == "1024x1024"
    assert openai_pixel_size("16:9", "1K") == "1536x1024"
    assert openai_pixel_size("9:16", "1K") == "1024x1536"

    assert openai_pixel_size("1:1", "2K") == "2048x2048"
    assert openai_pixel_size("16:9", "2K") == "2048x1152"
    assert openai_pixel_size("9:16", "2K") == "1152x2048"

    assert openai_pixel_size("1:1", "4K") == "2880x2880"
    assert openai_pixel_size("16:9", "4K") == "3840x2160"
    assert openai_pixel_size("9:16", "4K") == "2160x3840"


def test_image_controls_match_each_model() -> None:
    controls = image_control_catalog()

    assert controls["openai"]["qualities"] == ["low", "medium", "high", "xhigh", "max"]
    assert controls["openai"]["resolutions"] == ["1K", "2K", "4K"]
    flash = controls["google"][GEMINI_31_FLASH_IMAGE_MODEL]
    pro = controls["google"][GEMINI_3_PRO_IMAGE_MODEL]
    assert flash["qualities"] == ["minimal", "high"]
    assert flash["resolutions"] == ["0.5K", "1K", "2K", "4K"]
    assert pro["qualities"] == []
    assert pro["resolutions"] == ["1K", "2K", "4K"]
