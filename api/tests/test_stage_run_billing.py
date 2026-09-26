from app.services.api_pricing import (
    cost_anthropic_usage,
    cost_google_usage,
    cost_llamaparse_usage,
    cost_openai_usage,
)
from app.services.stage_run_billing import (
    build_api_usage,
    stage_run_completion_fields,
)


def test_openai_cost_uses_model_rates() -> None:
    call = cost_openai_usage(model="gpt-6-luna", input_tokens=1_000_000, output_tokens=500_000)

    assert call["input_cost_usd"] == 0.10
    assert call["output_cost_usd"] == 0.25
    assert call["cost_usd"] == 0.35


def test_build_api_usage_from_execution() -> None:
    usage = build_api_usage(
        {
            "model": "gpt-6-luna",
            "token_usage": {
                "input_tokens": 10_000,
                "output_tokens": 2_000,
            },
        },
    )

    assert len(usage["calls"]) == 1
    assert usage["totals"]["input_tokens"] == 10_000
    assert usage["totals"]["output_tokens"] == 2_000
    assert usage["totals"]["cost_usd"] > 0


def test_stage_run_completion_fields() -> None:
    fields = stage_run_completion_fields(
        {
            "model": "gpt-6-luna",
            "token_usage": {"input_tokens": 100, "output_tokens": 50},
        },
    )

    assert fields["cost_usd"] == fields["api_usage"]["totals"]["cost_usd"]
    assert len(fields["api_usage"]["calls"]) == 1


def test_llamaparse_cost() -> None:
    call = cost_llamaparse_usage(credit_count=80)

    assert call["credit_count"] == 80
    assert call["cost_usd"] == 0.1


def test_build_api_usage_includes_llamaparse_credits() -> None:
    usage = build_api_usage(
        {
            "model": "llamaparse",
            "token_usage": {},
            "page_count": 42,
        },
    )

    assert len(usage["calls"]) == 1
    assert usage["calls"][0]["provider"] == "llamaparse"
    assert usage["totals"]["credit_count"] == 42
    assert usage["totals"]["cost_usd"] == round(42 * 0.00125, 6)


def test_build_api_usage_routes_anthropic_provider() -> None:
    usage = build_api_usage(
        {
            "model": "claude-sonnet-5",
            "provider": "anthropic",
            "token_usage": {
                "input_tokens": 10_000,
                "output_tokens": 2_000,
            },
        },
    )

    assert len(usage["calls"]) == 1
    assert usage["calls"][0]["provider"] == "anthropic"
    assert usage["totals"]["cost_usd"] == cost_anthropic_usage(
        model="claude-sonnet-5",
        input_tokens=10_000,
        output_tokens=2_000,
    )["cost_usd"]


def test_build_api_usage_routes_google_provider() -> None:
    usage = build_api_usage(
        {
            "model": "gemini-3.7-flash",
            "provider": "google",
            "token_usage": {
                "input_tokens": 10_000,
                "output_tokens": 2_000,
            },
        },
    )

    assert len(usage["calls"]) == 1
    assert usage["calls"][0]["provider"] == "google"
    assert usage["totals"]["cost_usd"] == cost_google_usage(
        model="gemini-3.7-flash",
        input_tokens=10_000,
        output_tokens=2_000,
    )["cost_usd"]
