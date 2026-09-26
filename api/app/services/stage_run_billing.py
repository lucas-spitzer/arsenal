from __future__ import annotations

from typing import Any

from app.services.api_pricing import cost_image_usage, cost_llamaparse_usage, cost_llm_usage


def _token_count(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

    return 0


def _sum_call_costs(calls: list[dict[str, Any]]) -> float:
    return round(sum(float(call.get("cost_usd") or 0) for call in calls), 6)


def build_api_usage(
    execution: dict[str, Any],
    *,
    extra_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build provider-level usage and USD cost from a stage execution payload."""

    calls: list[dict[str, Any]] = []
    token_usage = execution.get("token_usage") or {}

    if isinstance(token_usage, dict) and any(token_usage.values()):
        input_tokens = _token_count(token_usage, "input_tokens", "prompt_tokens")
        output_tokens = _token_count(token_usage, "output_tokens", "completion_tokens")

        if input_tokens or output_tokens:
            provider = str(execution.get("provider") or "openai").strip().lower()
            calls.append(
                cost_llm_usage(
                    provider=provider,
                    model=str(execution.get("model") or "unknown"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                ),
            )

    llamaparse_credits = execution.get("llamaparse_credit_count")
    if not isinstance(llamaparse_credits, int) or llamaparse_credits <= 0:
        llamaparse_credits = execution.get("page_count")

    model_name = str(execution.get("model") or "").strip().lower()
    if model_name == "llamaparse" and isinstance(llamaparse_credits, int) and llamaparse_credits > 0:
        calls.append(cost_llamaparse_usage(credit_count=llamaparse_credits))

    if extra_calls:
        calls.extend(extra_calls)

    totals = {
        "input_tokens": sum(int(call.get("input_tokens") or 0) for call in calls),
        "output_tokens": sum(int(call.get("output_tokens") or 0) for call in calls),
        "character_count": sum(int(call.get("character_count") or 0) for call in calls),
        "search_count": sum(int(call.get("search_count") or 0) for call in calls),
        "credit_count": sum(int(call.get("credit_count") or 0) for call in calls),
        "cost_usd": _sum_call_costs(calls),
    }

    return {
        "calls": calls,
        "totals": totals,
    }


def image_stage_run_completion_fields(
    *,
    provider: str,
    model: str,
    token_usage: dict[str, int],
) -> dict[str, Any]:
    """Image tokens bill at image rates, so skip the LLM token pricing path."""
    call = cost_image_usage(
        provider=provider,
        model=model,
        input_tokens=int(token_usage.get("input_tokens") or 0),
        output_tokens=int(token_usage.get("output_tokens") or 0),
    )
    api_usage = build_api_usage({}, extra_calls=[call])
    return {
        "model": model,
        "token_usage": token_usage,
        "api_usage": api_usage,
        "cost_usd": api_usage["totals"]["cost_usd"],
    }


def stage_run_completion_fields(
    execution: dict[str, Any],
    *,
    extra_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    api_usage = build_api_usage(execution, extra_calls=extra_calls)

    return {
        "model": execution.get("model"),
        "token_usage": execution.get("token_usage") or {},
        "api_usage": api_usage,
        "cost_usd": api_usage["totals"]["cost_usd"],
    }
