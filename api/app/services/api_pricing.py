from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.services.llm.model_catalog import catalog_list_price
from app.services.tts.catalog import tts_catalog_list_price


@dataclass(frozen=True)
class TokenRates:
    input_per_million: float
    output_per_million: float


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    return float(raw)


# Published list prices; override via env when your contract differs.
OPENAI_MODEL_RATES: dict[str, TokenRates] = {
    "gpt-5.6-sol": TokenRates(
        input_per_million=_float_env("OPENAI_GPT56_SOL_INPUT_PER_M", 5.00),
        output_per_million=_float_env("OPENAI_GPT56_SOL_OUTPUT_PER_M", 30.00),
    ),
    "gpt-5.6-terra": TokenRates(
        input_per_million=_float_env("OPENAI_GPT56_TERRA_INPUT_PER_M", 2.00),
        output_per_million=_float_env("OPENAI_GPT56_TERRA_OUTPUT_PER_M", 12.00),
    ),
    "gpt-5.6-luna": TokenRates(
        input_per_million=_float_env("OPENAI_GPT56_LUNA_INPUT_PER_M", 0.20),
        output_per_million=_float_env("OPENAI_GPT56_LUNA_OUTPUT_PER_M", 1.20),
    ),
}

DEFAULT_OPENAI_RATES = TokenRates(
    input_per_million=_float_env("OPENAI_DEFAULT_INPUT_PER_M", 0.20),
    output_per_million=_float_env("OPENAI_DEFAULT_OUTPUT_PER_M", 1.20),
)

# Published list prices — override via env before relying on cost_usd for billing.
ANTHROPIC_MODEL_RATES: dict[str, TokenRates] = {
    "claude-opus-5": TokenRates(
        input_per_million=_float_env("ANTHROPIC_OPUS_INPUT_PER_M", 5.00),
        output_per_million=_float_env("ANTHROPIC_OPUS_OUTPUT_PER_M", 25.00),
    ),
    "claude-sonnet-5": TokenRates(
        input_per_million=_float_env("ANTHROPIC_SONNET_INPUT_PER_M", 2.00),
        output_per_million=_float_env("ANTHROPIC_SONNET_OUTPUT_PER_M", 10.00),
    ),
    "claude-haiku-4-5": TokenRates(
        input_per_million=_float_env("ANTHROPIC_HAIKU_INPUT_PER_M", 1.00),
        output_per_million=_float_env("ANTHROPIC_HAIKU_OUTPUT_PER_M", 5.00),
    ),
}

DEFAULT_ANTHROPIC_RATES = TokenRates(
    input_per_million=_float_env("ANTHROPIC_DEFAULT_INPUT_PER_M", 2.00),
    output_per_million=_float_env("ANTHROPIC_DEFAULT_OUTPUT_PER_M", 10.00),
)

GOOGLE_MODEL_RATES: dict[str, TokenRates] = {
    "gemini-3.7-flash": TokenRates(
        input_per_million=_float_env("GOOGLE_GEMINI_37_FLASH_INPUT_PER_M", 0.75),
        output_per_million=_float_env("GOOGLE_GEMINI_37_FLASH_OUTPUT_PER_M", 3.75),
    ),
}

DEFAULT_GOOGLE_RATES = TokenRates(
    input_per_million=_float_env("GOOGLE_DEFAULT_INPUT_PER_M", 0.75),
    output_per_million=_float_env("GOOGLE_DEFAULT_OUTPUT_PER_M", 3.75),
)

LLAMAPARSE_PRICE_PER_CREDIT = _float_env("LLAMAPARSE_PRICE_PER_CREDIT", 0.00125)

# Server-side web search is billed per search on top of tokens ($10 / 1k
# searches at both providers' list price).
ANTHROPIC_WEB_SEARCH_PRICE_PER_SEARCH = _float_env("ANTHROPIC_WEB_SEARCH_PRICE_PER_SEARCH", 0.01)
OPENAI_WEB_SEARCH_PRICE_PER_SEARCH = _float_env("OPENAI_WEB_SEARCH_PRICE_PER_SEARCH", 0.01)

# ElevenLabs API list for Multilingual v2 / v3 is $0.10 / 1K characters
# ($100 / 1M). Override if your plan's effective rate differs.
ELEVENLABS_PRICE_PER_CHARACTER = _float_env("ELEVENLABS_PRICE_PER_CHARACTER", 0.0001)

# Speechify Starter / PAYG list is $10 / 1M characters. Override for Pro ($8)
# or Scale ($6).
SPEECHIFY_PRICE_PER_CHARACTER = _float_env("SPEECHIFY_PRICE_PER_CHARACTER", 0.00001)

# Cartesia Pro sticker: $5 / 100K credits ≈ $50 / 1M characters.
CARTESIA_PRICE_PER_CHARACTER = _float_env("CARTESIA_PRICE_PER_CHARACTER", 0.00005)

# Gemini 3.1 Flash TTS converted sticker: $40 / 1M characters.
GOOGLE_TTS_PRICE_PER_CHARACTER = _float_env("GOOGLE_TTS_PRICE_PER_CHARACTER", 0.00004)

_TTS_PRICE_ENV: dict[str, str] = {
    "speechify": "SPEECHIFY_PRICE_PER_CHARACTER",
    "elevenlabs": "ELEVENLABS_PRICE_PER_CHARACTER",
    "cartesia": "CARTESIA_PRICE_PER_CHARACTER",
    "google": "GOOGLE_TTS_PRICE_PER_CHARACTER",
}

_TTS_DEFAULT_RATES: dict[str, float] = {
    "speechify": SPEECHIFY_PRICE_PER_CHARACTER,
    "elevenlabs": ELEVENLABS_PRICE_PER_CHARACTER,
    "cartesia": CARTESIA_PRICE_PER_CHARACTER,
    "google": GOOGLE_TTS_PRICE_PER_CHARACTER,
}


def _round_usd(value: float) -> float:
    return round(value, 6)


def openai_rates_for_model(model: str | None) -> TokenRates:
    normalized = (model or "").strip().lower()

    if normalized in OPENAI_MODEL_RATES:
        return OPENAI_MODEL_RATES[normalized]

    # Longest prefix first so "gpt-5.6-luna-..." beats a shorter family prefix.
    for key, rates in sorted(
        OPENAI_MODEL_RATES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if normalized.startswith(key):
            return rates

    catalog = catalog_list_price(model)
    if catalog is not None:
        return TokenRates(input_per_million=catalog[0], output_per_million=catalog[1])

    return DEFAULT_OPENAI_RATES


def cost_openai_usage(
    *,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    rates = openai_rates_for_model(model)
    input_cost = (input_tokens / 1_000_000) * rates.input_per_million
    output_cost = (output_tokens / 1_000_000) * rates.output_per_million
    total = input_cost + output_cost

    return {
        "provider": "openai",
        "model": model or "unknown",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": _round_usd(input_cost),
        "output_cost_usd": _round_usd(output_cost),
        "cost_usd": _round_usd(total),
    }


def anthropic_rates_for_model(model: str | None) -> TokenRates:
    normalized = (model or "").strip().lower()

    for key, rates in sorted(
        ANTHROPIC_MODEL_RATES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if normalized.startswith(key):
            return rates

    catalog = catalog_list_price(model)
    if catalog is not None:
        return TokenRates(input_per_million=catalog[0], output_per_million=catalog[1])

    return DEFAULT_ANTHROPIC_RATES


def cost_anthropic_usage(
    *,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    rates = anthropic_rates_for_model(model)
    input_cost = (input_tokens / 1_000_000) * rates.input_per_million
    output_cost = (output_tokens / 1_000_000) * rates.output_per_million
    total = input_cost + output_cost

    return {
        "provider": "anthropic",
        "model": model or "unknown",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": _round_usd(input_cost),
        "output_cost_usd": _round_usd(output_cost),
        "cost_usd": _round_usd(total),
    }


def google_rates_for_model(model: str | None) -> TokenRates:
    normalized = (model or "").strip().lower()

    if normalized in GOOGLE_MODEL_RATES:
        return GOOGLE_MODEL_RATES[normalized]

    for key, rates in sorted(
        GOOGLE_MODEL_RATES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if normalized.startswith(key):
            return rates

    catalog = catalog_list_price(model)
    if catalog is not None:
        return TokenRates(input_per_million=catalog[0], output_per_million=catalog[1])

    return DEFAULT_GOOGLE_RATES


def cost_google_usage(
    *,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    rates = google_rates_for_model(model)
    input_cost = (input_tokens / 1_000_000) * rates.input_per_million
    output_cost = (output_tokens / 1_000_000) * rates.output_per_million
    total = input_cost + output_cost

    return {
        "provider": "google",
        "model": model or "unknown",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": _round_usd(input_cost),
        "output_cost_usd": _round_usd(output_cost),
        "cost_usd": _round_usd(total),
    }


def cost_llm_usage(
    *,
    provider: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    if provider == "anthropic":
        return cost_anthropic_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    if provider == "google":
        return cost_google_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    return cost_openai_usage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def cost_web_search_usage(*, provider: str, search_count: int) -> dict[str, Any]:
    rate = (
        ANTHROPIC_WEB_SEARCH_PRICE_PER_SEARCH
        if provider == "anthropic"
        else OPENAI_WEB_SEARCH_PRICE_PER_SEARCH
    )

    return {
        "provider": provider,
        "model": "web_search",
        "search_count": search_count,
        "cost_usd": _round_usd(search_count * rate),
    }


def cost_llamaparse_usage(*, credit_count: int) -> dict[str, Any]:
    total = credit_count * LLAMAPARSE_PRICE_PER_CREDIT

    return {
        "provider": "llamaparse",
        "credit_count": credit_count,
        "cost_usd": _round_usd(total),
    }


def _tts_character_rate(*, provider: str, model: str | None) -> float:
    env_name = _TTS_PRICE_ENV.get(provider)
    if env_name:
        raw = os.getenv(env_name)
        if raw is not None and raw.strip():
            return float(raw)

    catalog = tts_catalog_list_price(model)
    if catalog is not None:
        return catalog / 1_000_000.0

    return _TTS_DEFAULT_RATES.get(provider, ELEVENLABS_PRICE_PER_CHARACTER)


def cost_elevenlabs_usage(*, model: str | None, character_count: int) -> dict[str, Any]:
    rate = _tts_character_rate(provider="elevenlabs", model=model)
    total = character_count * rate

    return {
        "provider": "elevenlabs",
        "model": model or "unknown",
        "character_count": character_count,
        "cost_usd": _round_usd(total),
    }


def cost_speechify_usage(*, model: str | None, character_count: int) -> dict[str, Any]:
    rate = _tts_character_rate(provider="speechify", model=model)
    total = character_count * rate

    return {
        "provider": "speechify",
        "model": model or "unknown",
        "character_count": character_count,
        "cost_usd": _round_usd(total),
    }


def cost_tts_usage(
    *,
    provider: str,
    model: str | None,
    character_count: int,
) -> dict[str, Any]:
    rate = _tts_character_rate(provider=provider, model=model)
    total = character_count * rate

    return {
        "provider": provider,
        "model": model or "unknown",
        "character_count": character_count,
        "cost_usd": _round_usd(total),
    }
