from __future__ import annotations

from typing import Any

import pytest

from app.services.llm.gemini_client import GeminiClient, _thinking_level
from app.services.llm.reasoning import ReasoningSettings


def test_thinking_level_maps_effort() -> None:
    assert _thinking_level(None) is None
    assert _thinking_level(ReasoningSettings()) is None
    assert _thinking_level(ReasoningSettings(effort="none")) is None
    assert _thinking_level(ReasoningSettings(effort="low")) == "low"
    assert _thinking_level(ReasoningSettings(effort="minimal")) == "low"
    assert _thinking_level(ReasoningSettings(effort="xhigh")) == "high"


def test_gemini_complete_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    captured: dict[str, Any] = {}

    class FakeModels:
        def generate_content(self, **kwargs: Any) -> Any:
            captured.update(kwargs)

            class Usage:
                prompt_token_count = 11
                candidates_token_count = 7
                thoughts_token_count = 3
                total_token_count = 21

            class Response:
                text = '{"ok": true}'
                usage_metadata = Usage()

            return Response()

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["api_key"] = kwargs.get("api_key")
            self.models = FakeModels()

    monkeypatch.setattr("app.services.llm.gemini_client.genai.Client", FakeClient)

    client = GeminiClient(model="gemini-3.8-flash", reasoning=ReasoningSettings(effort="high"))
    result = client.complete_json(system_prompt="sys", user_prompt="user")

    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gemini-3.8-flash"
    assert result.provider == "google"
    assert result.content == {"ok": True}
    assert result.token_usage["input_tokens"] == 11
    assert result.token_usage["output_tokens"] == 10
    assert result.token_usage["total_tokens"] == 21


def test_gemini_complete_json_with_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    captured: dict[str, Any] = {}

    class FakePart:
        @staticmethod
        def from_bytes(**kwargs: Any) -> dict[str, Any]:
            return {"part": kwargs}

    class FakeModels:
        def generate_content(self, **kwargs: Any) -> Any:
            captured.update(kwargs)

            class Usage:
                prompt_token_count = 4
                candidates_token_count = 2
                thoughts_token_count = 0
                total_token_count = 6

            class Response:
                text = '{"title": "Sheet", "body_html": "<p>ok</p>"}'
                usage_metadata = Usage()

            return Response()

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.models = FakeModels()

    monkeypatch.setattr("app.services.llm.gemini_client.genai.Client", FakeClient)
    monkeypatch.setattr("app.services.llm.gemini_client.types.Part", FakePart)

    client = GeminiClient(model="gemini-3.8-flash")
    result = client.complete_json_with_document(
        system_prompt="sys",
        user_prompt="user",
        document_bytes=b"%PDF-1.4",
        document_mime="application/pdf",
    )

    assert captured["model"] == "gemini-3.8-flash"
    assert captured["contents"][0]["part"]["mime_type"] == "application/pdf"
    assert result.content["title"] == "Sheet"
