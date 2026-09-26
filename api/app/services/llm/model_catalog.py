"""Curated catalog of selectable LLM models.

Hand-maintained, not fetched from providers: adding a newly released model is a
one-line edit here, which is the whole point — surface swappable models without
code changes elsewhere.

- ``capability_tier`` is a curated 1 (lightest) .. 5 (most capable) judgment.
  No in-repo benchmark exists, so this is intentionally coarse guidance for the
  settings UI's "capability vs cost" view, not a measured score.
- ``input_per_million`` / ``output_per_million`` are indicative published list
  prices in USD per million tokens. They are ``None`` when not reliably known.
  They feed billing only as a *fallback* in app.services.api_pricing for models
  absent from its env-overridable rate tables; an env override always wins.

Kept dependency-light (stdlib + app.llm_defaults) so app.services.api_pricing can
import it without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.llm_defaults import (
    GEMINI_37_FLASH_MODEL,
    GPT_6_ASTRA_MODEL,
    GPT_6_LUNA_MODEL,
    GPT_6_SOL_MODEL,
    HAIKU_45_MODEL,
    OPUS_55_MODEL,
    SONNET_5_MODEL,
)


@dataclass(frozen=True)
class CatalogModel:
    model: str
    provider: str
    display_name: str
    capability_tier: int
    supports_reasoning: bool
    reasoning_modes: tuple[str, ...]
    context_window: int | None = None
    input_per_million: float | None = None
    output_per_million: float | None = None


# Prices are USD per million tokens (standard on-demand, short context).
# OpenAI GPT-6 Astra/Sol/Luna list prices are $10/$50, $2/$10, and $0.10/$0.50.
# Gemini 3.7 Flash uses introductory list prices through 2026-12-31.
MODEL_CATALOG: tuple[CatalogModel, ...] = (
    # --- Anthropic ---
    CatalogModel(
        model=OPUS_55_MODEL,
        provider="anthropic",
        display_name="Claude Opus 5.5",
        capability_tier=4,
        supports_reasoning=True,
        reasoning_modes=("adaptive",),
        context_window=1_000_000,
        input_per_million=4.00,
        output_per_million=20.00,
    ),
    CatalogModel(
        model=SONNET_5_MODEL,
        provider="anthropic",
        display_name="Claude Sonnet 5",
        capability_tier=3,
        supports_reasoning=True,
        reasoning_modes=("adaptive",),
        context_window=1_000_000,
        input_per_million=2.00,
        output_per_million=10.00,
    ),
    CatalogModel(
        model=HAIKU_45_MODEL,
        provider="anthropic",
        display_name="Claude Haiku 4.5",
        capability_tier=2,
        supports_reasoning=True,
        reasoning_modes=("budget",),
        context_window=200_000,
        input_per_million=1.00,
        output_per_million=5.00,
    ),
    # --- OpenAI ---
    CatalogModel(
        model=GPT_6_ASTRA_MODEL,
        provider="openai",
        display_name="GPT-6 Astra",
        capability_tier=5,
        supports_reasoning=True,
        reasoning_modes=("effort",),
        context_window=1_050_000,
        input_per_million=10.00,
        output_per_million=50.00,
    ),
    CatalogModel(
        model=GPT_6_SOL_MODEL,
        provider="openai",
        display_name="GPT-6 Sol",
        capability_tier=3,
        supports_reasoning=True,
        reasoning_modes=("effort",),
        context_window=1_050_000,
        input_per_million=2.00,
        output_per_million=10.00,
    ),
    CatalogModel(
        model=GPT_6_LUNA_MODEL,
        provider="openai",
        display_name="GPT-6 Luna",
        capability_tier=1,
        supports_reasoning=True,
        reasoning_modes=("effort",),
        context_window=1_050_000,
        input_per_million=0.10,
        output_per_million=0.50,
    ),
    # --- Google ---
    CatalogModel(
        model=GEMINI_37_FLASH_MODEL,
        provider="google",
        display_name="Gemini 3.7 Flash",
        capability_tier=1,
        supports_reasoning=True,
        reasoning_modes=("effort",),
        context_window=1_048_576,
        input_per_million=0.75,
        output_per_million=3.75,
    ),
)


def get_catalog_model(model: str | None) -> CatalogModel | None:
    """Match a provider model id to a catalog entry (exact, then longest prefix)."""
    normalized = (model or "").strip().lower()

    if not normalized:
        return None

    for entry in MODEL_CATALOG:
        if entry.model.lower() == normalized:
            return entry

    # Longest prefix first so "gpt-6-luna-..." beats a shorter family prefix.
    for entry in sorted(MODEL_CATALOG, key=lambda e: len(e.model), reverse=True):
        if normalized.startswith(entry.model.lower()):
            return entry

    return None


SELECTABLE_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "google"})


def validate_selection(provider: str | None, model: str | None) -> str | None:
    """Validate a workspace's stage selection; return an error message or None.

    Permits models absent from the curated catalog (new releases should be
    selectable without a code change), but rejects unsupported providers, empty
    models, and a known model paired with the wrong provider.
    """
    normalized_provider = (provider or "").strip().lower()
    normalized_model = (model or "").strip()

    if normalized_provider not in SELECTABLE_PROVIDERS:
        return f"Unsupported provider '{provider}'."

    if not normalized_model:
        return "Model is required."

    entry = get_catalog_model(normalized_model)
    if entry is not None and entry.provider != normalized_provider:
        return (
            f"Model '{normalized_model}' belongs to provider '{entry.provider}', "
            f"not '{normalized_provider}'."
        )

    return None


def catalog_list_price(model: str | None) -> tuple[float, float] | None:
    """Indicative (input, output) USD per million tokens, or None if unknown."""
    entry = get_catalog_model(model)

    if entry is None or entry.input_per_million is None or entry.output_per_million is None:
        return None

    return (entry.input_per_million, entry.output_per_million)
