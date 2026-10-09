from __future__ import annotations

import pytest

from app.config import get_settings
from app.llm_defaults import (
    GEMINI_3_PRO_IMAGE_MODEL,
    GEMINI_NANO_BANANA_21_MODEL,
    GROK_IMAGINE_IMAGE_2_MODEL,
    OPENAI_IMAGE_FLARE_MODEL,
    OPENAI_IMAGE_SUNBURST_MODEL,
)
from app.mathesys.study_material.images import (
    ImageRequest,
    google_api_image_size,
    image_control_catalog,
    openai_pixel_size,
    resolve_image_settings,
    xai_image_call,
)
from app.mathesys.study_material.inputs import ComponentFile
from app.services.stage_run_billing import image_stage_run_completion_fields


def _pin_env_image_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDY_MATERIAL_IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("STUDY_MATERIAL_OPENAI_IMAGE_MODEL", OPENAI_IMAGE_SUNBURST_MODEL)
    monkeypatch.setenv("STUDY_MATERIAL_GOOGLE_IMAGE_MODEL", GEMINI_NANO_BANANA_21_MODEL)
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


def test_resolve_drops_half_k_on_nano_banana(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {
            "provider": "google",
            "model": GEMINI_NANO_BANANA_21_MODEL,
            "image_size": "0.5K",
            "thinking_level": "high",
        },
    )
    replaced = resolve_image_settings(
        {"provider": "google", "model": "gemini-3.1-flash-image"},
    )

    assert resolved["image_size"] == "1K"
    assert resolved["thinking_level"] == "high"
    assert replaced["model"] == GEMINI_NANO_BANANA_21_MODEL
    assert replaced["thinking_level"] == "medium"
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
        default_model=GEMINI_NANO_BANANA_21_MODEL,
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
    flash = controls["google"][GEMINI_NANO_BANANA_21_MODEL]
    pro = controls["google"][GEMINI_3_PRO_IMAGE_MODEL]
    assert flash["qualities"] == ["minimal", "medium", "high"]
    assert flash["resolutions"] == ["1K", "2K", "4K"]
    assert pro["qualities"] == []
    assert pro["resolutions"] == ["1K", "2K", "4K"]
    assert controls["xai"]["qualities"] == ["low", "medium"]
    assert controls["xai"]["resolutions"] == ["1K", "1.5K", "2K"]


def test_resolve_clamps_grok_quality_and_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_env_image_default(monkeypatch)

    resolved = resolve_image_settings(
        {
            "provider": "xai",
            "model": GROK_IMAGINE_IMAGE_2_MODEL,
            "quality": "high",
            "resolution": "4K",
        },
    )
    kept = resolve_image_settings(
        {
            "provider": "xai",
            "quality": "low",
            "resolution": "1.5K",
        },
    )

    assert resolved["model"] == GROK_IMAGINE_IMAGE_2_MODEL
    assert resolved["quality"] == "medium"
    assert resolved["resolution"] == "1K"
    assert kept["quality"] == "low"
    assert kept["resolution"] == "1.5K"
    get_settings.cache_clear()


def test_xai_image_call_uses_json_for_references() -> None:
    generate_url, generate_body = xai_image_call(
        GROK_IMAGINE_IMAGE_2_MODEL,
        ImageRequest(prompt="A field sketch of a compass", aspect_ratio="16:9", quality="medium", resolution="2K"),
    )
    edit_url, edit_body = xai_image_call(
        GROK_IMAGINE_IMAGE_2_MODEL,
        ImageRequest(
            prompt="A field sketch of a compass",
            aspect_ratio="3:2",
            quality="low",
            resolution="1.5K",
            references=[ComponentFile(filename="ref.png", mime_type="image/png", content=b"png")],
        ),
    )

    assert generate_url.endswith("/images/generations")
    assert generate_body["model"] == GROK_IMAGINE_IMAGE_2_MODEL
    assert generate_body["prompt"] == "A field sketch of a compass"
    assert generate_body["resolution"] == "2k"
    assert generate_body["quality"] == "medium"
    assert "image" not in generate_body
    assert edit_url.endswith("/images/edits")
    assert edit_body["resolution"] == "1.5k"
    assert edit_body["image"]["url"].startswith("data:image/png;base64,")


def test_grok_image_billing_uses_the_per_image_table() -> None:
    billed = image_stage_run_completion_fields(
        provider="xai",
        model=GROK_IMAGINE_IMAGE_2_MODEL,
        token_usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        settings={"resolution": "2K", "quality": "medium", "reference_count": 1},
    )

    assert billed["cost_usd"] == 0.09
