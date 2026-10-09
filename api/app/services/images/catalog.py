"""Curated catalog of design-tab image models selectable as the workspace default.

``price_per_image`` is USD for one generated image at a 1K-class output
(output tokens only, no reference images). It feeds the Stage Models UI.
Billing stays on the token rates in app.services.api_pricing.

GPT Image 2.5 Sunburst bills image output at $30 per million tokens. At the
design tab's default quality ``high`` and 1024x1024, that is 1,756 tokens,
$0.05268, shown as $0.053.
https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst

Nano Banana 2.1 bills image output at $30 per million tokens. Google's
published 1K (1024x1024) equivalent is 1,120 tokens, $0.0336. 2K is $0.0504
and 4K is $0.113. Input is $1.50 per million tokens. The stage row uses the
1K sticker. Thinking defaults to medium.
https://ai.google.dev/gemini-api/docs/pricing

Grok Imagine Image 2.0 bills per image. The sticker is 1K at medium quality,
$0.06, which is the Design Image default. Low is $0.04 / $0.05 / $0.06 and
medium is $0.06 / $0.07 / $0.08 at 1K, 1.5K, and 2K. Each reference image
adds $0.01.
https://docs.x.ai/developers/models/grok-imagine-image-2.0
"""

from __future__ import annotations

from dataclasses import dataclass

from app.image_defaults import STUDY_MATERIAL_IMAGE_ACTION
from app.llm_defaults import (
    GEMINI_NANO_BANANA_21_MODEL,
    GROK_IMAGINE_IMAGE_2_MODEL,
    OPENAI_IMAGE_SUNBURST_MODEL,
)
from app.services.api_pricing import XAI_IMAGE_1K_MEDIUM_PRICE
from app.mathesys.study_material.images import effective_stage_image_quality

# Rounded from $0.05268 (1,756 tokens at $30 / 1M).
OPENAI_IMAGE_HIGH_1024_PRICE = 0.053
NANO_BANANA_21_1K_PRICE = 0.0336


@dataclass(frozen=True)
class ImageCatalogModel:
    model: str
    provider: str
    display_name: str
    price_per_image: float | None = None
    capability_tier: int = 3


IMAGE_MODEL_CATALOG: tuple[ImageCatalogModel, ...] = (
    ImageCatalogModel(
        model=GEMINI_NANO_BANANA_21_MODEL,
        provider="google",
        display_name="Nano Banana 2.1",
        price_per_image=NANO_BANANA_21_1K_PRICE,
        capability_tier=4,
    ),
    ImageCatalogModel(
        model=OPENAI_IMAGE_SUNBURST_MODEL,
        provider="openai",
        display_name="GPT Image 2.5 Sunburst",
        price_per_image=OPENAI_IMAGE_HIGH_1024_PRICE,
        capability_tier=2,
    ),
    ImageCatalogModel(
        model=GROK_IMAGINE_IMAGE_2_MODEL,
        provider="xai",
        display_name="Grok Imagine 2.0",
        price_per_image=XAI_IMAGE_1K_MEDIUM_PRICE,
        capability_tier=3,
    ),
)

IMAGE_SELECTABLE_PROVIDERS: frozenset[str] = frozenset({"openai", "google", "xai"})

IMAGE_CATALOG_BY_MODEL: dict[str, ImageCatalogModel] = {
    entry.model: entry for entry in IMAGE_MODEL_CATALOG
}


def get_image_catalog_model(model: str | None) -> ImageCatalogModel | None:
    normalized = (model or "").strip().lower()
    if not normalized:
        return None
    for entry in IMAGE_MODEL_CATALOG:
        if entry.model.lower() == normalized:
            return entry
    return None


def validate_image_selection(provider: str | None, model: str | None) -> str | None:
    normalized_provider = (provider or "").strip().lower()
    normalized_model = (model or "").strip()

    if normalized_provider not in IMAGE_SELECTABLE_PROVIDERS:
        return f"Unsupported image provider '{provider}'."

    if not normalized_model:
        return "Model is required."

    entry = get_image_catalog_model(normalized_model)
    if entry is None:
        return f"Unknown image model '{normalized_model}'."

    if entry.provider != normalized_provider:
        return (
            f"Model '{normalized_model}' belongs to provider '{entry.provider}', "
            f"not '{normalized_provider}'."
        )

    return None


@dataclass(frozen=True)
class ImageStageDefault:
    provider: str
    model: str
    quality: str


def image_default_from_rows(rows: list[dict[str, object]]) -> ImageStageDefault | None:
    """Workspace Design Image override, or None when the row is missing or invalid."""
    for row in rows:
        action = str(row.get("stage_action") or "").strip()
        if action != STUDY_MATERIAL_IMAGE_ACTION:
            continue
        provider = str(row.get("provider") or "").strip().lower()
        model = str(row.get("model") or "").strip()
        if validate_image_selection(provider, model) is not None:
            return None
        quality = effective_stage_image_quality(
            provider,
            model,
            str(row.get("image_quality") or "") or None,
        )
        return ImageStageDefault(provider=provider, model=model, quality=quality)
    return None


__all__ = [
    "IMAGE_MODEL_CATALOG",
    "IMAGE_SELECTABLE_PROVIDERS",
    "ImageCatalogModel",
    "ImageStageDefault",
    "get_image_catalog_model",
    "image_default_from_rows",
    "validate_image_selection",
]
