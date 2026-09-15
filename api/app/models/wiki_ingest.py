from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EntryKind = Literal["term", "concept", "insight"]
Importance = Literal["essential", "supporting", "contextual"]
Resolution = Literal["new", "merge", "conflict"]
EvidenceStatus = Literal["linked", "weak", "unlinked"]
BatchStatus = Literal[
    "transcribing",
    "transcribed",
    "structuring",
    "draft",
    "committed",
    "discarded",
    "failed",
]


class WikiIngestCreate(BaseModel):
    notes: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    chapter_hint: str | None = None
    title: str | None = None


class WikiIngestEvidence(BaseModel):
    segment_id: str
    sequence_index: int | None = None
    page: int | None = None
    similarity: float | None = None
    preview: str | None = None
    reader_link: str | None = None


class WikiIngestSimilarEntry(BaseModel):
    id: str
    label: str
    similarity: float


class WikiIngestEntry(BaseModel):
    index: int
    label: str
    entry_kind: EntryKind = "concept"
    definition: str
    aliases: list[str] = Field(default_factory=list)
    pronunciation: str | None = None
    importance: Importance = "supporting"
    prerequisite_labels: list[str] = Field(default_factory=list)
    note_excerpt: str = ""

    canonical_slug: str = ""
    resolution: Resolution = "new"
    existing_entry_id: str | None = None
    existing_definition: str | None = None
    similar_entries: list[WikiIngestSimilarEntry] = Field(default_factory=list)

    evidence_status: EvidenceStatus = "unlinked"
    evidence: list[WikiIngestEvidence] = Field(default_factory=list)

    include: bool = True


class WikiIngestChapter(BaseModel):
    chapter_id: str
    title: str
    sequence_index: int


class WikiIngestAttachment(BaseModel):
    order: int
    filename: str
    mime_type: str
    storage_path: str
    byte_size: int


class WikiIngestBatchResponse(BaseModel):
    id: str
    workspace_id: str
    source_id: str | None
    production_run_id: str | None = None
    title: str
    raw_notes: str
    chapter_hint: str | None
    chapter: WikiIngestChapter | None
    status: BatchStatus
    entries: list[WikiIngestEntry]
    unparsed_fragments: list[str]
    attachments: list[WikiIngestAttachment] = Field(default_factory=list)
    transcription_error: str | None = None
    model: str | None
    cost_usd: float | None
    committed_entry_ids: list[str]
    committed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WikiIngestBatchUpdate(BaseModel):
    title: str | None = None
    raw_notes: str | None = None
    entries: list[WikiIngestEntry] | None = None


class WikiIngestCommitResponse(BaseModel):
    batch: WikiIngestBatchResponse
    inserted_entry_ids: list[str]
    updated_entry_ids: list[str]


class WikiIngestCommitConflict(BaseModel):
    """409 payload: review state drifted against the current wiki."""

    detail: str
    drifted_indexes: list[int]
    batch: WikiIngestBatchResponse


def batch_row_to_response(row: dict[str, Any]) -> WikiIngestBatchResponse:
    return WikiIngestBatchResponse.model_validate(
        {
            **row,
            "entries": row.get("entries") or [],
            "unparsed_fragments": row.get("unparsed_fragments") or [],
            "attachments": row.get("attachments") or [],
            "committed_entry_ids": row.get("committed_entry_ids") or [],
        },
    )
