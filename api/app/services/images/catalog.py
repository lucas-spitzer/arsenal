"""Curated catalog of design-tab image models selectable as the workspace default.

``price_per_image`` is USD for one generated image at a 1K-class output
(output tokens only, no reference images). It feeds the Stage Models UI.
Billing stays on the token rates in app.services.api_pricing.

GPT Image 2.5 Sunburst bills image output at $30 per million tokens. At the
design tab's default quality ``high`` and 1024x1024, that is 1,756 tokens,
$0.05268, shown as $0.053.
https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst

Gemini 3.1 Flash Image bills image output at $60 per million tokens. Google's
published 1K (1024x1024) equivalent is 1,120 tokens, $0.067. The design tab
can still request 2K or 4K on a component. The stage row uses the 1K sticker
so it lines up with the OpenAI 1024 figure.
https://ai.google.dev/gemini-api/docs/pricing
"""

from __future__ import annotations

from dataclasses import dataclass

from app.image_defaults import STUDY_MATERIAL_IMAGE_ACTION
from app.llm_defaults import (
    GEMINI_31_FLASH_IMAGE_MODEL,
    OPENAI_IMAGE_SUNBURST_MODEL,
)
from app.mathesys.study_material.images import effective_stage_image_quality

# Rounded from $0.05268 (1,756 tokens at $30 / 1M).
OPENAI_IMAGE_HIGH_1024_PRICE = 0.053
GEMINI_FLASH_IMAGE_1K_PRICE = 0.067


@dataclass(frozen=True)
class ImageCatalogModel:
    model: str
    provider: str
    display_name: str
    price_per_image: float | None = None
    capability_tier: int = 3


IMAGE_MODEL_CATALOG: tuple[ImageCatalogModel, ...] = (
    ImageCatalogModel(
        model=GEMINI_31_FLASH_IMAGE_MODEL,
        provider="google",
        display_name="Gemini 3.1 Flash Image",
        price_per_image=GEMINI_FLASH_IMAGE_1K_PRICE,
        capability_tier=4,
    ),
    ImageCatalogModel(
        model=OPENAI_IMAGE_SUNBURST_MODEL,
        provider="openai",
        display_name="GPT Image 2.5 Sunburst",
        price_per_image=OPENAI_IMAGE_HIGH_1024_PRICE,
        capability_tier=3,
    ),
)

IMAGE_SELECTABLE_PROVIDERS: frozenset[str] = frozenset({"openai", "google"})

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
