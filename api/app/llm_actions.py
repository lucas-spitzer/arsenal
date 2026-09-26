"""Canonical registry of every LLM-calling pipeline stage ("action").

Single source of truth for the default provider/model of each stage that calls
an LLM. Lives at app top level (not under app.services.llm) to avoid an import
cycle with app.config, mirroring app.llm_defaults.

Runtime resolution order (see app.config._resolve_llm_action):
workspace override -> action model env var -> registry default below.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.llm_defaults import (
    GPT_6_LUNA_MODEL,
    GPT_6_SOL_MODEL,
    SONNET_5_MODEL,
)


@dataclass(frozen=True)
class LLMAction:
    key: str
    label: str
    provider: str
    model: str
    model_env: str


LLM_ACTIONS: tuple[LLMAction, ...] = (
    LLMAction(
        "source_research",
        "Source Research",
        "openai",
        GPT_6_LUNA_MODEL,
        "SOURCE_RESEARCH_MODEL",
    ),
    # Needs a provider/model with server-side web search support.
    LLMAction(
        "source_web_enrichment",
        "Source Web Enrichment",
        "anthropic",
        SONNET_5_MODEL,
        "SOURCE_WEB_ENRICHMENT_MODEL",
    ),
    LLMAction(
        "wiki_structuring",
        "Wiki Structuring",
        "openai",
        GPT_6_SOL_MODEL,
        "WIKI_STRUCTURING_MODEL",
    ),
    LLMAction(
        "wiki_revise",
        "Wiki Revise",
        "openai",
        GPT_6_SOL_MODEL,
        "WIKI_REVISE_MODEL",
    ),
    LLMAction(
        "qngen_draft",
        "Assessment Draft",
        "openai",
        GPT_6_LUNA_MODEL,
        "DRAFT_MODEL",
    ),
    LLMAction(
        "qngen_critique",
        "Assessment Critique",
        "anthropic",
        SONNET_5_MODEL,
        "CRITIQUE_MODEL",
    ),
    LLMAction(
        "reader_define",
        "Reader Define",
        "openai",
        GPT_6_LUNA_MODEL,
        "READER_DEFINE_MODEL",
    ),
    LLMAction(
        "study_material",
        "Study Material",
        "openai",
        GPT_6_SOL_MODEL,
        "STUDY_MATERIAL_MODEL",
    ),
    LLMAction(
        "study_material_orchestrator",
        "Study Material Orchestrator",
        "openai",
        GPT_6_SOL_MODEL,
        "STUDY_MATERIAL_ORCHESTRATOR_MODEL",
    ),
)

LLM_ACTION_BY_KEY: dict[str, LLMAction] = {action.key: action for action in LLM_ACTIONS}

LLM_ACTION_DEFAULTS: dict[str, tuple[str, str]] = {
    action.key: (action.provider, action.model) for action in LLM_ACTIONS
}

LLM_GLOBAL_DEFAULT: tuple[str, str] = ("anthropic", SONNET_5_MODEL)
