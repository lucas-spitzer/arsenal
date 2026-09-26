from __future__ import annotations

import pytest

from app.llm_actions import LLM_ACTION_DEFAULTS
from app.models.llm import build_model_catalog_response
from app.services import api_pricing
from app.services.llm.model_catalog import (
    MODEL_CATALOG,
    catalog_list_price,
    get_catalog_model,
)


def test_every_action_default_model_is_in_catalog() -> None:
    catalog_ids = {entry.model for entry in MODEL_CATALOG}

    for provider, model in LLM_ACTION_DEFAULTS.values():
        assert model in catalog_ids, f"{model} ({provider}) missing from catalog"


def test_catalog_contains_only_selected_models() -> None:
    catalog_ids = {entry.model for entry in MODEL_CATALOG}

    assert catalog_ids == {
        "claude-opus-5-5",
        "claude-sonnet-5",
        "claude-haiku-4-5-20251001",
        "gpt-6-astra",
        "gpt-6-sol",
        "gpt-6-luna",
        "gemini-3.7-flash",
    }


def test_capability_tiers_within_range() -> None:
    for entry in MODEL_CATALOG:
        assert 1 <= entry.capability_tier <= 5


def test_get_catalog_model_exact_and_prefix() -> None:
    assert get_catalog_model("gpt-6-luna").display_name == "GPT-6 Luna"
    # A dated snapshot should resolve by longest-prefix, not collapse to a sibling.
    assert get_catalog_model("gpt-6-luna-2026-01-01").model == "gpt-6-luna"
    assert get_catalog_model("gpt-6-sol-2026-01-01").model == "gpt-6-sol"
    assert get_catalog_model("gemini-3.7-flash").display_name == "Gemini 3.7 Flash"
    assert get_catalog_model("nonexistent-model") is None
    assert get_catalog_model(None) is None


def test_catalog_list_price_known_and_unknown() -> None:
    assert catalog_list_price("claude-haiku-4-5-20251001") == (1.00, 5.00)
    assert catalog_list_price("gemini-3.7-flash") == (0.75, 3.75)
    # A model absent from the catalog has no list price.
    assert catalog_list_price("nonexistent-model") is None


def test_openai_rates_fall_back_to_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_pricing,
        "catalog_list_price",
        lambda model: (1.23, 4.56) if model == "future-openai" else None,
    )

    rates = api_pricing.openai_rates_for_model("future-openai")

    assert rates.input_per_million == 1.23
    assert rates.output_per_million == 4.56


def test_anthropic_rates_fall_back_to_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_pricing,
        "catalog_list_price",
        lambda model: (2.00, 8.00) if model == "future-anthropic" else None,
    )

    rates = api_pricing.anthropic_rates_for_model("future-anthropic")

    assert rates.input_per_million == 2.00
    assert rates.output_per_million == 8.00


def test_google_rates_use_catalog_and_explicit_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_pricing,
        "catalog_list_price",
        lambda model: (999.0, 999.0),
    )

    rates = api_pricing.google_rates_for_model("gemini-3.7-flash")

    assert rates.input_per_million == 0.75
    assert rates.output_per_million == 3.75


def test_explicit_rate_table_wins_over_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    # gpt-6-luna is in the explicit table; catalog fallback must not be consulted.
    monkeypatch.setattr(
        api_pricing,
        "catalog_list_price",
        lambda model: (999.0, 999.0),
    )

    rates = api_pricing.openai_rates_for_model("gpt-6-luna")

    assert rates.input_per_million == 0.10


def test_build_model_catalog_response_serializes_all_entries() -> None:
    response = build_model_catalog_response()

    assert len(response.models) == len(MODEL_CATALOG)
    haiku = next(m for m in response.models if m.model == "claude-haiku-4-5-20251001")
    assert haiku.reasoning_modes == ["budget"]
    assert haiku.supports_reasoning is True
