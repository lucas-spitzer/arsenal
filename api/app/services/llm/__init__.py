"""Provider-agnostic LLM client layer.

Stages depend only on the ``LLMClient`` protocol and obtain a concrete client
through ``get_llm_client(action)``. Provider and model for each action are
resolved from configuration at runtime, so any step can be repointed at any
current or future model without code changes.
"""

from app.llm_defaults import HAIKU_55_MODEL
from app.services.llm.anthropic_client import AnthropicClient
from app.services.llm.base import LLMClient, LLMCompletionResult
from app.services.llm.factory import (
    ActionOverride,
    get_llm_client,
    overrides_from_rows,
    reset_workspace_overrides,
    resolve_action,
    set_workspace_overrides,
)
from app.services.llm.gemini_client import GeminiClient
from app.services.llm.openai_adapter import OpenAILLMClient
from app.services.llm.reasoning import ReasoningSettings

__all__ = [
    "ActionOverride",
    "AnthropicClient",
    "GeminiClient",
    "HAIKU_55_MODEL",
    "LLMClient",
    "LLMCompletionResult",
    "OpenAILLMClient",
    "ReasoningSettings",
    "get_llm_client",
    "overrides_from_rows",
    "reset_workspace_overrides",
    "resolve_action",
    "set_workspace_overrides",
]
