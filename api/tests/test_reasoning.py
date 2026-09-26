from __future__ import annotations

import types
from typing import Any

import pytest

from app.services.llm.anthropic_client import (
    AnthropicClient,
    _anthropic_reasoning_kwargs,
    _supports_adaptive,
)
from app.services.llm.factory import (
    get_llm_client,
    overrides_from_rows,
    reset_workspace_overrides,
    set_workspace_overrides,
)
from app.services.llm.reasoning import ReasoningSettings


@pytest.fixture(autouse=True)
def _clear_overrides():
    token = set_workspace_overrides({})
    try:
        yield
    finally:
        reset_workspace_overrides(token)


def test_overrides_from_rows_carries_reasoning() -> None:
    rows = [
        {
            "stage_action": "source_web_enrichment",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "reasoning_effort": "High",
            "reasoning_tokens": None,
        },
        {
            "stage_action": "wiki_structuring",
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "reasoning_effort": None,
            "reasoning_tokens": 8000,
        },
    ]

    overrides = overrides_from_rows(rows)

    assert overrides["source_web_enrichment"].reasoning == ReasoningSettings(effort="high")
    assert overrides["wiki_structuring"].reasoning == ReasoningSettings(
        thinking_budget_tokens=8000
    )


def test_overrides_from_rows_no_reasoning_is_none() -> None:
    rows = [{"stage_action": "wiki_structuring", "provider": "openai", "model": "gpt-5.4"}]

    assert overrides_from_rows(rows)["wiki_structuring"].reasoning is None


def test_supports_adaptive_by_family() -> None:
    assert _supports_adaptive("claude-opus-5-5")
    assert _supports_adaptive("claude-sonnet-5")
    assert _supports_adaptive("claude-opus-4-8")
    assert _supports_adaptive("claude-sonnet-4-6")
    assert not _supports_adaptive("claude-haiku-4-5-20251001")


def test_adaptive_kwargs_use_output_config_effort() -> None:
    kwargs = _anthropic_reasoning_kwargs(
        "claude-opus-4-8",
        ReasoningSettings(effort="high"),
        max_tokens=16384,
    )

    assert kwargs == {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}


def test_budget_kwargs_clamped_below_max_tokens() -> None:
    kwargs = _anthropic_reasoning_kwargs(
        "claude-haiku-4-5-20251001",
        ReasoningSettings(thinking_budget_tokens=999_999),
        max_tokens=16384,
    )

    assert kwargs == {"thinking": {"type": "enabled", "budget_tokens": 16383}}


def test_empty_reasoning_emits_no_kwargs() -> None:
    assert _anthropic_reasoning_kwargs("claude-opus-4-8", None, max_tokens=16384) == {}
    assert (
        _anthropic_reasoning_kwargs("claude-opus-4-8", ReasoningSettings(), max_tokens=16384) == {}
    )


def test_anthropic_request_includes_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeTextBlock:
        type = "text"
        text = '{"ok": true}'

    class FakeUsage:
        input_tokens = 4
        output_tokens = 2

    class FakeResponse:
        model = "claude-opus-4-8"
        content = [FakeTextBlock()]
        usage = FakeUsage()

    class FakeMessages:
        def create(self, **kwargs: Any) -> FakeResponse:
            captured.update(kwargs)
            return FakeResponse()

    client = AnthropicClient(
        api_key="test-key",
        model="claude-opus-4-8",
        reasoning=ReasoningSettings(effort="medium"),
    )
    client.client = types.SimpleNamespace(messages=FakeMessages())  # type: ignore[assignment]

    client.complete_json(system_prompt="sys", user_prompt="user")

    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"] == {"effort": "medium"}


def test_get_llm_client_forwards_reasoning_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    token = set_workspace_overrides(
        {
            "source_research": overrides_from_rows(
                [
                    {
                        "stage_action": "source_research",
                        "provider": "openai",
                        "model": "gpt-5.4",
                        "reasoning_effort": "low",
                    },
                ],
            )["source_research"],
        },
    )
    try:
        client = get_llm_client("source_research")
    finally:
        reset_workspace_overrides(token)

    assert client._client.reasoning_effort == "low"
