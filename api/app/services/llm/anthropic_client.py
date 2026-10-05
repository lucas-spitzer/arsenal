from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic, BadRequestError

from app.config import get_settings
from app.llm_defaults import SONNET_55_MODEL
from app.services.llm.base import LLMCompletionResult
from app.services.llm.reasoning import ReasoningSettings

_DEFAULT_MODEL = SONNET_55_MODEL

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_PREFILL_ERROR_MARKERS = ("prefill", "must end with a user message")

# Models known not to support assistant prefill (skip the failing attempt).
_PREFILL_UNSUPPORTED_MODELS: set[str] = set()

# Model families that take adaptive thinking + output_config.effort. Older
# families (Haiku 4.5, *-4-5) instead use a manual thinking.budget_tokens cap.
# See docs/internal/llm-reasoning-levels.md for the full mode matrix.
_ADAPTIVE_MODEL_MARKERS = (
    "sonnet-5",
    "opus-5",
    "sonnet-4-6",
    "opus-4-6",
    "opus-4-7",
    "opus-4-8",
    "fable",
    "mythos",
)
_MIN_THINKING_BUDGET_TOKENS = 1024


def _supports_adaptive(model: str) -> bool:
    lowered = model.lower()
    return any(marker in lowered for marker in _ADAPTIVE_MODEL_MARKERS)


def _anthropic_reasoning_kwargs(
    model: str,
    reasoning: ReasoningSettings | None,
    *,
    max_tokens: int,
) -> dict[str, Any]:
    """Translate provider-neutral reasoning into Anthropic request params.

    Returns ``{}`` when no reasoning is requested so the default path issues the
    same request as before. Adaptive-family models get
    ``thinking={"type":"adaptive"}`` plus ``output_config.effort``; older
    budget-mode models get an explicit ``budget_tokens`` cap (kept below
    ``max_tokens``, as the API requires).
    """
    if reasoning is None or reasoning.is_empty():
        return {}

    if _supports_adaptive(model):
        kwargs: dict[str, Any] = {"thinking": {"type": "adaptive"}}
        if reasoning.effort:
            kwargs["output_config"] = {"effort": reasoning.effort}
        return kwargs

    if reasoning.thinking_budget_tokens:
        budget = max(
            _MIN_THINKING_BUDGET_TOKENS,
            min(reasoning.thinking_budget_tokens, max_tokens - 1),
        )
        return {"thinking": {"type": "enabled", "budget_tokens": budget}}

    return {}


def _prefill_disabled() -> bool:
    prefill = get_settings().llm.anthropic_json_prefill
    return prefill in {
        "0",
        "false",
        "no",
        "off",
    }


def _model_supports_prefill(model: str) -> bool:
    if _prefill_disabled():
        return False
    return model not in _PREFILL_UNSUPPORTED_MODELS


def _first_text(response: Any) -> str:
    parts: list[str] = []

    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")

    return "".join(parts)


def _text_blocks(response: Any) -> list[str]:
    return [
        getattr(block, "text", "") or ""
        for block in getattr(response, "content", None) or []
        if getattr(block, "type", None) == "text"
    ]


def _salvage_items_object(raw: str) -> dict[str, Any] | None:
    """Best-effort recovery when the model returns truncated JSON."""
    items_key = raw.find('"items"')
    if items_key == -1:
        return None

    array_start = raw.find("[", items_key)
    if array_start == -1:
        return None

    objects: list[Any] = []
    index = array_start + 1

    while index < len(raw):
        while index < len(raw) and raw[index] in " \t\n\r,":
            index += 1

        if index >= len(raw) or raw[index] == "]":
            break

        if raw[index] != "{":
            break

        obj_start = index
        depth = 0
        in_string = False
        escape = False

        while index < len(raw):
            char = raw[index]

            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                index += 1
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    fragment = raw[obj_start : index + 1]
                    try:
                        parsed = json.loads(fragment)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        objects.append(parsed)
                    index += 1
                    break

            index += 1
        else:
            break

    if objects:
        return {"items": objects}

    return None


def _try_parse_with_repair(text: str) -> dict[str, Any] | None:
    for candidate in (text, _FENCE_RE.sub("", text).strip()):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict):
            return parsed

    salvaged = _salvage_items_object(text)
    if salvaged is not None:
        return salvaged

    start = text.find("{")
    if start == -1:
        return None

    fragment = text[start:].rstrip()
    closers = ("", "}", "]}", "\"}", "\"]}", "\"}]}")

    for end in range(len(fragment), max(start, len(fragment) - 5000), -1):
        tail = fragment[:end].rstrip().rstrip(",")
        for suffix in closers:
            try:
                parsed = json.loads(tail + suffix)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    return None


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating fences/preamble/truncation."""
    candidate = raw.strip()

    for attempt in (candidate, _FENCE_RE.sub("", candidate).strip()):
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed

    repaired = _try_parse_with_repair(candidate)
    if repaired is not None:
        return repaired

    raise RuntimeError("Anthropic response was not a JSON object.")


class AnthropicClient:
    """Anthropic Messages API client conforming to the ``LLMClient`` protocol.

    Structured output uses assistant prefill of ``"{"`` when the model supports
    it, with automatic fallback to user-only messages and defensive JSON parsing
    for models that reject prefill.
    """

    provider = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        reasoning: ReasoningSettings | None = None,
    ) -> None:
        settings = get_settings()
        resolved_key = api_key or settings.llm.anthropic_api_key

        if not resolved_key:
            raise RuntimeError("Missing required environment variable: ANTHROPIC_API_KEY")

        self.model = model or _DEFAULT_MODEL
        self.max_tokens = max_tokens or settings.llm.anthropic_max_tokens
        self.temperature = temperature
        self.reasoning = reasoning
        self.client = Anthropic(api_key=resolved_key)

    def _messages(self, user_prompt: str, *, use_prefill: bool) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "user", "content": user_prompt}]
        if use_prefill:
            messages.append({"role": "assistant", "content": "{"})
        return messages

    def _is_prefill_error(self, exc: BadRequestError) -> bool:
        message = str(exc).lower()
        return any(marker in message for marker in _PREFILL_ERROR_MARKERS)

    def _create_response(
        self,
        *,
        resolved_model: str,
        system_prompt: str,
        user_prompt: str,
        use_prefill: bool,
    ) -> Any:
        request: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": self._messages(user_prompt, use_prefill=use_prefill),
        }

        if self.temperature is not None:
            request["temperature"] = self.temperature

        request.update(
            _anthropic_reasoning_kwargs(
                resolved_model,
                self.reasoning,
                max_tokens=self.max_tokens,
            ),
        )

        return self.client.messages.create(**request)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> LLMCompletionResult:
        resolved_model = model or self.model
        use_prefill = _model_supports_prefill(resolved_model)

        try:
            response = self._create_response(
                resolved_model=resolved_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                use_prefill=use_prefill,
            )
        except BadRequestError as exc:
            if use_prefill and self._is_prefill_error(exc):
                _PREFILL_UNSUPPORTED_MODELS.add(resolved_model)
                use_prefill = False
                response = self._create_response(
                    resolved_model=resolved_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    use_prefill=False,
                )
            else:
                raise

        raw_text = _first_text(response)
        if use_prefill:
            raw_text = "{" + raw_text

        content = _parse_json_object(raw_text)

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        return LLMCompletionResult(
            content=content,
            model=str(getattr(response, "model", resolved_model)),
            provider=self.provider,
            token_usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )

    def complete_json_with_web_search(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_searches: int = 5,
    ) -> LLMCompletionResult:
        resolved_model = model or self.model

        # No assistant prefill here: prefilling "{" would force the model to
        # answer immediately instead of issuing web_search tool calls first.
        request: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max(1, max_searches),
                },
            ],
        }

        if self.temperature is not None:
            request["temperature"] = self.temperature

        request.update(
            _anthropic_reasoning_kwargs(
                resolved_model,
                self.reasoning,
                max_tokens=self.max_tokens,
            ),
        )

        response = self.client.messages.create(**request)

        # The model interleaves commentary text between searches; the JSON
        # answer is the last text block. Fall back to the concatenated text
        # (with repair) when the last block alone doesn't parse.
        content: dict[str, Any] | None = None
        for block_text in reversed(_text_blocks(response)):
            parsed = _try_parse_with_repair(block_text.strip())
            if parsed is not None:
                content = parsed
                break

        if content is None:
            content = _parse_json_object(_first_text(response))

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        server_tool_use = getattr(usage, "server_tool_use", None)
        web_search_requests = int(getattr(server_tool_use, "web_search_requests", 0) or 0)

        return LLMCompletionResult(
            content=content,
            model=str(getattr(response, "model", resolved_model)),
            provider=self.provider,
            token_usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "web_search_requests": web_search_requests,
            },
        )
