from __future__ import annotations

from typing import Any

import pytest

from app.services.api_pricing import cost_anthropic_usage, cost_llm_usage
from app.services.llm.anthropic_client import _parse_json_object
from app.llm_defaults import SONNET_5_MODEL
from app.services.llm.factory import get_llm_client, resolve_action
from app.services.llm.openai_adapter import OpenAILLMClient
from app.services.openai_client import OpenAICompletionResult


class FakeOpenAIBackend:
    def __init__(self) -> None:
        self.model = "gpt-4o-mini"

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None):
        return OpenAICompletionResult(
            content={"ok": True},
            model=model or self.model,
            token_usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        )


def test_resolve_action_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_EXTRACT_KNOWLEDGE_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_EXTRACT_KNOWLEDGE_MODEL", raising=False)

    provider, model = resolve_action("extract_knowledge")

    assert provider == "anthropic"
    assert model == SONNET_5_MODEL


def test_resolve_action_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_QNGEN_DRAFT_PROVIDER", "openai")
    monkeypatch.setenv("DRAFT_MODEL", "gpt-4o")

    provider, model = resolve_action("qngen_draft")

    assert provider == "openai"
    assert model == "gpt-4o"


def test_resolve_action_openai_stage_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LLM_SOURCE_RESEARCH_PROVIDER", "SOURCE_RESEARCH_MODEL"):
        monkeypatch.delenv(var, raising=False)

    provider, model = resolve_action("source_research")

    assert provider == "openai"
    assert model == "gpt-6-luna"


def test_resolve_action_uses_dedicated_model_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_WIKI_STRUCTURING_PROVIDER", raising=False)
    monkeypatch.setenv("WIKI_STRUCTURING_MODEL", "gpt-4o")

    provider, model = resolve_action("wiki_structuring")

    assert provider == "openai"
    assert model == "gpt-4o"


def test_openai_adapter_adds_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = OpenAILLMClient()
    client._client = FakeOpenAIBackend()  # type: ignore[assignment]

    result = client.complete_json(system_prompt="sys", user_prompt="user")

    assert result.provider == "openai"
    assert result.content == {"ok": True}
    assert result.token_usage["input_tokens"] == 5


def test_parse_json_object_tolerates_fences() -> None:
    parsed = _parse_json_object('```json\n{"items": []}\n```')

    assert parsed == {"items": []}


def test_parse_json_object_salvages_truncated_items() -> None:
    from app.services.llm.anthropic_client import _parse_json_object

    truncated = """{"items": [
        {"term_label": "Alpha", "definition": "First"},
        {"term_label": "Beta", "definition": "Second"},
        {"term_label": "Gamma", "definition": "Thi"""

    parsed = _parse_json_object(truncated)

    assert len(parsed["items"]) == 2
    assert parsed["items"][0]["term_label"] == "Alpha"
    assert parsed["items"][1]["term_label"] == "Beta"


def test_anthropic_client_retries_without_prefill(monkeypatch: pytest.MonkeyPatch) -> None:
    from anthropic import BadRequestError

    from app.services.llm.anthropic_client import AnthropicClient, _PREFILL_UNSUPPORTED_MODELS

    _PREFILL_UNSUPPORTED_MODELS.discard("claude-sonnet-4-6")

    class FakeTextBlock:
        type = "text"
        text = '{"objectives": []}'

    class FakeUsage:
        input_tokens = 10
        output_tokens = 5

    class FakeResponse:
        model = "claude-sonnet-4-6"
        content = [FakeTextBlock()]
        usage = FakeUsage()

    calls: list[bool] = []

    class FakeMessages:
        def create(self, **kwargs: Any) -> FakeResponse:
            messages = kwargs["messages"]
            use_prefill = len(messages) > 1 and messages[-1]["role"] == "assistant"
            calls.append(use_prefill)
            if use_prefill:
                raise BadRequestError(
                    message="This model does not support assistant message prefill.",
                    response=__import__("httpx").Response(400, request=__import__("httpx").Request("POST", "https://api.anthropic.com")),
                    body={"error": {"message": "prefill unsupported"}},
                )
            return FakeResponse()

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    client.client = __import__("types").SimpleNamespace(messages=FakeMessages())  # type: ignore[assignment]

    result = client.complete_json(system_prompt="sys", user_prompt='Return {"objectives": []}')

    assert calls == [True, False]
    assert result.content == {"objectives": []}
    assert "claude-sonnet-4-6" in _PREFILL_UNSUPPORTED_MODELS


def test_cost_anthropic_usage() -> None:
    call = cost_anthropic_usage(
        model="claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )

    assert call["provider"] == "anthropic"
    assert call["cost_usd"] > 0


def test_cost_llm_usage_dispatches_by_provider() -> None:
    anthropic = cost_llm_usage(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
    )
    openai = cost_llm_usage(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=500,
    )

    assert anthropic["provider"] == "anthropic"
    assert openai["provider"] == "openai"


def test_get_llm_client_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EXTRACT_KNOWLEDGE_PROVIDER", "openai")
    monkeypatch.setenv("LLM_EXTRACT_KNOWLEDGE_MODEL", "gpt-4o-mini")

    client = get_llm_client("extract_knowledge")

    assert client.provider == "openai"
