from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.config import get_settings
from app.llm_defaults import DEFAULT_OPENAI_MODEL


@dataclass(frozen=True)
class OpenAICompletionResult:
    content: dict[str, Any]
    model: str
    token_usage: dict[str, int]


def _parse_json_object_lenient(raw: str) -> dict[str, Any]:
    """Parse a JSON object from web-search output, tolerating fences/preamble.

    Unlike ``complete_json``, the Responses API with tools cannot enforce a
    JSON response format, so the answer may carry citations or prose around it.
    """
    candidate = raw.strip()

    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()

    for attempt in (candidate,):
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            continue
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

    raise RuntimeError("OpenAI web-search response was not a JSON object.")


def _accepts_custom_temperature(model: str) -> bool:
    # Imported lazily: model_catalog lives under app.services.llm, whose package
    # init imports this module.
    from app.services.llm.model_catalog import get_catalog_model

    # GPT-6 reasoning models reject every temperature except the API default.
    entry = get_catalog_model(model)
    if entry is None:
        return True
    return not (entry.provider == "openai" and entry.supports_reasoning)


class OpenAIClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        settings = get_settings()
        resolved_key = api_key or settings.llm.openai_api_key

        if not resolved_key:
            raise RuntimeError("Missing required environment variable: OPENAI_API_KEY")

        self.model = model or DEFAULT_OPENAI_MODEL
        self.reasoning_effort = reasoning_effort
        self.client = OpenAI(api_key=resolved_key)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> OpenAICompletionResult:
        request: dict[str, Any] = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        # Sent only when a workspace opts in, so non-reasoning models and the
        # default path issue the exact same request as before.
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort

        response = self.client.chat.completions.create(**request)

        message_content = response.choices[0].message.content

        if not message_content:
            raise RuntimeError("OpenAI returned an empty response.")

        parsed = json.loads(message_content)

        if not isinstance(parsed, dict):
            raise RuntimeError("OpenAI response was not a JSON object.")

        usage = response.usage
        token_usage = {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }

        return OpenAICompletionResult(
            content=parsed,
            model=response.model,
            token_usage=token_usage,
        )

    def complete_json_with_web_search(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_searches: int = 5,
    ) -> OpenAICompletionResult:
        # Web search is only exposed through the Responses API; the tool does
        # not take a max-uses cap there, so max_searches is prompt-enforced.
        del max_searches
        request: dict[str, Any] = {
            "model": model or self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "tools": [{"type": "web_search"}],
        }

        if self.reasoning_effort:
            request["reasoning"] = {"effort": self.reasoning_effort}

        response = self.client.responses.create(**request)

        output_text = (getattr(response, "output_text", None) or "").strip()
        if not output_text:
            raise RuntimeError("OpenAI returned an empty response.")

        parsed = _parse_json_object_lenient(output_text)

        web_search_requests = sum(
            1
            for item in getattr(response, "output", None) or []
            if getattr(item, "type", "") == "web_search_call"
        )

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        return OpenAICompletionResult(
            content=parsed,
            model=str(getattr(response, "model", request["model"])),
            token_usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "web_search_requests": web_search_requests,
            },
        )

    def complete_text(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> OpenAICompletionResult:
        """Free-text chat completion for the conversational assistant.

        `messages` is the running user/assistant turn history (each item is
        ``{"role": "user"|"assistant", "content": str}``); the system prompt and
        any retrieved context are prepended by the caller.
        """
        resolved_model = model or self.model
        request: dict[str, Any] = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
        }

        if temperature is not None and _accepts_custom_temperature(resolved_model):
            request["temperature"] = temperature

        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort

        response = self.client.chat.completions.create(**request)

        message_content = response.choices[0].message.content
        if not message_content:
            raise RuntimeError("OpenAI returned an empty response.")

        usage = response.usage
        token_usage = {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }

        return OpenAICompletionResult(
            content={"text": message_content},
            model=response.model,
            token_usage=token_usage,
        )
