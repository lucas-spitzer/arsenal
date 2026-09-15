from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WikiEntryCreate(BaseModel):
    """Single manual entry, no LLM (quick add)."""

    preferred_label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    entry_kind: Literal["term", "concept", "insight"] = "concept"
    importance: Literal["essential", "supporting", "contextual"] = "supporting"
    aliases: list[str] = Field(default_factory=list)
    pronunciation: str | None = None
    origin: dict[str, Any] | None = None


class WikiReviseRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)


class WikiReviseProposal(BaseModel):
    definition: str
    preferred_label: str | None = None
    aliases: list[str] | None = None


class WikiEntryUpdate(BaseModel):
    preferred_label: str | None = None
    definition: str | None = None
    entry_kind: Literal["term", "concept", "insight"] | None = None
    importance: Literal["essential", "supporting", "contextual"] | None = None
    aliases: list[str] | None = None
    pronunciation: str | None = None


class WikiEntryResponse(BaseModel):
    id: str
    workspace_id: str
    preferred_label: str
    canonical_slug: str
    definition: str
    pronunciation: str | None
    aliases: list[str]
    prerequisites: list[str]
    importance: str
    entry_kind: str
    status: str
    evidence: list[dict[str, Any]]
    origin: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WikiDisputeResponse(BaseModel):
    id: str
    workspace_id: str
    wiki_entry_id: str | None
    term_label: str
    existing_definition: str | None
    proposed_definition: str
    stage_run_id: str | None
    source_id: str | None
    status: str
    created_at: datetime
