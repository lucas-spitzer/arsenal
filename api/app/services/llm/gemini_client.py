"""Google Gemini client conforming to the ``LLMClient`` protocol."""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.llm_defaults import GEMINI_38_FLASH_MODEL
from app.services.llm.base import LLMCompletionResult
from app.services.llm.reasoning import ReasoningSettings

_THINKING_LEVELS = frozenset({"low", "medium", "high"})
_THINKING_ALIASES = {
    "minimal": "low",
    "min": "low",
    "xhigh": "high",
    "max": "high",
}


def _thinking_level(reasoning: ReasoningSettings | None) -> str | None:
    if reasoning is None or reasoning.is_empty() or not reasoning.effort:
        return None

    effort = reasoning.effort.strip().lower()
    if effort in {"none", "off"}:
        return None

    mapped = _THINKING_ALIASES.get(effort, effort)
    if mapped not in _THINKING_LEVELS:
        return None
    return mapped


def _parse_json_object_lenient(raw: str) -> dict[str, Any]:
    candidate = raw.strip()

    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    raise RuntimeError("Gemini response was not a JSON object.")


def _usage_tokens(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    thoughts = int(getattr(usage, "thoughts_token_count", 0) or 0)
    output_tokens += thoughts
    total = int(getattr(usage, "total_token_count", 0) or 0) or (input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
    }


def _grounding_search_count(response: Any) -> int:
    candidate = (getattr(response, "candidates", None) or [None])[0]
    metadata = getattr(candidate, "grounding_metadata", None) if candidate is not None else None
    chunks = getattr(metadata, "grounding_chunks", None) or []
    return len(chunks)


class GeminiClient:
    provider = "google"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        reasoning: ReasoningSettings | None = None,
    ) -> None:
        settings = get_settings()
        resolved_key = api_key or settings.llm.google_api_key

        if not resolved_key:
            raise RuntimeError("Missing required environment variable: GEMINI_API_KEY")

        self.model = model or GEMINI_38_FLASH_MODEL
        self.reasoning = reasoning
        self.client = genai.Client(api_key=resolved_key)

    def _generate_config(
        self,
        *,
        system_prompt: str,
        json_mime: bool,
        tools: list[Any] | None = None,
    ) -> types.GenerateContentConfig:
        kwargs: dict[str, Any] = {"system_instruction": system_prompt}
        if json_mime:
            kwargs["response_mime_type"] = "application/json"
        if tools:
            kwargs["tools"] = tools

        level = _thinking_level(self.reasoning)
        if level:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=level)

        return types.GenerateContentConfig(**kwargs)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> LLMCompletionResult:
        resolved_model = model or self.model
        response = self.client.models.generate_content(
            model=resolved_model,
            contents=user_prompt,
            config=self._generate_config(system_prompt=system_prompt, json_mime=True),
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        if not raw_text:
            raise RuntimeError("Gemini returned an empty response.")

        return LLMCompletionResult(
            content=_parse_json_object_lenient(raw_text),
            model=resolved_model,
            provider=self.provider,
            token_usage=_usage_tokens(response),
        )

    def complete_json_with_document(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        document_bytes: bytes,
        document_mime: str,
        model: str | None = None,
    ) -> LLMCompletionResult:
        resolved_model = model or self.model
        contents = [
            types.Part.from_bytes(data=document_bytes, mime_type=document_mime),
            user_prompt,
        ]
        response = self.client.models.generate_content(
            model=resolved_model,
            contents=contents,
            config=self._generate_config(system_prompt=system_prompt, json_mime=True),
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        if not raw_text:
            raise RuntimeError("Gemini returned an empty response.")

        return LLMCompletionResult(
            content=_parse_json_object_lenient(raw_text),
            model=resolved_model,
            provider=self.provider,
            token_usage=_usage_tokens(response),
        )

    def complete_json_with_web_search(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_searches: int = 5,
    ) -> LLMCompletionResult:
        del max_searches
        resolved_model = model or self.model
        response = self.client.models.generate_content(
            model=resolved_model,
            contents=user_prompt,
            config=self._generate_config(
                system_prompt=system_prompt,
                json_mime=False,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        if not raw_text:
            raise RuntimeError("Gemini returned an empty response.")

        token_usage = _usage_tokens(response)
        token_usage["web_search_requests"] = _grounding_search_count(response)

        return LLMCompletionResult(
            content=_parse_json_object_lenient(raw_text),
            model=resolved_model,
            provider=self.provider,
            token_usage=token_usage,
        )
