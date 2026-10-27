from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from app.repositories.retrieval import RetrievalRepository
from app.services.embeddings import EmbeddingClient, get_embedding_client
from app.services.lesson_text import locator_label


@dataclass(frozen=True)
class RetrievedChunk:
    """One retrieved passage, ready to cite and (for source text) deep-link."""

    kind: Literal["segment", "wiki", "lesson"]
    label: str
    text: str
    similarity: float
    reader_link: str | None = None
    locator: dict[str, Any] = field(default_factory=dict)

    def to_citation(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "snippet": self.text[:280],
            "similarity": round(self.similarity, 4),
            "reader_link": self.reader_link,
            "locator": self.locator,
        }


def build_reader_link(source_id: str, sequence_index: int) -> str:
    """Deep link into the Reader by STABLE segment index.

    We anchor on ndr_segments.sequence_index, never page number: pages reflow
    when the reader changes font size, but the segment ordering is immutable
    (ndr_segments_source_sequence_key). The Reader resolves seq -> spread at
    render time and highlights the segment.
    """
    return f"/app/reader/{source_id}?seg={sequence_index}"


def build_lesson_link(lesson_id: str, resource_id: str | None = None) -> str:
    """Open the Academy ELO tab on one class (and highlight a file when given)."""
    link = f"/app/elo/{lesson_id}"
    return f"{link}?resource={resource_id}" if resource_id else link


# A thread focused on one class pulls more of that class's material.
FOCUSED_LESSON_COUNT = 8


class RetrievalService:
    def __init__(
        self,
        repository: RetrievalRepository,
        *,
        embedding_client: EmbeddingClient | None = None,
        threshold: float = 0.3,
        segment_count: int = 8,
        wiki_count: int = 6,
        lesson_count: int = 6,
    ) -> None:
        self.repository = repository
        self._embedding_client = embedding_client
        self.threshold = threshold
        self.segment_count = segment_count
        self.wiki_count = wiki_count
        self.lesson_count = lesson_count

    @property
    def embedding_client(self) -> EmbeddingClient:
        if self._embedding_client is None:
            self._embedding_client = get_embedding_client()
        return self._embedding_client

    async def retrieve(
        self,
        query: str,
        workspace_id: str,
        *,
        source_ids: list[str] | None = None,
        lesson_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        query = query.strip()
        if not query:
            return []

        # embed() returns one vector per input; we send exactly one.
        vectors = await asyncio.to_thread(self.embedding_client.embed, [query])
        embedding = vectors[0]

        segment_rows = await self.repository.match_segments(
            embedding=embedding,
            workspace_id=workspace_id,
            threshold=self.threshold,
            count=self.segment_count,
            source_ids=source_ids,
        )
        wiki_rows = await self.repository.match_wiki_entries(
            embedding=embedding,
            workspace_id=workspace_id,
            threshold=self.threshold,
            count=self.wiki_count,
        )
        # Lesson material is searched even when source_ids narrows the books.
        lesson_rows = await self.repository.match_lesson_chunks(
            embedding=embedding,
            workspace_id=workspace_id,
            threshold=self.threshold,
            count=max(self.lesson_count, FOCUSED_LESSON_COUNT) if lesson_ids else self.lesson_count,
            lesson_ids=lesson_ids or None,
        )

        chunks = [
            *(self._segment_chunk(row) for row in segment_rows),
            *(self._wiki_chunk(row) for row in wiki_rows),
            *(self._lesson_chunk(row) for row in lesson_rows),
        ]
        chunks.sort(key=lambda chunk: chunk.similarity, reverse=True)
        return chunks

    @staticmethod
    def _segment_chunk(row: dict[str, Any]) -> RetrievedChunk:
        chapter = row.get("chapter_title")
        page = (row.get("locator") or {}).get("page")
        label_parts = [part for part in (chapter, f"p.{page}" if page else None) if part]
        label = " · ".join(label_parts) or "Source text"
        return RetrievedChunk(
            kind="segment",
            label=label,
            text=row.get("text", ""),
            similarity=float(row.get("similarity", 0.0)),
            reader_link=build_reader_link(row["source_id"], row["sequence_index"]),
            locator={
                "source_id": row["source_id"],
                "sequence_index": row["sequence_index"],
                "chapter_sequence": row.get("chapter_sequence"),
                "page": page,
            },
        )

    @staticmethod
    def _lesson_chunk(row: dict[str, Any]) -> RetrievedChunk:
        lesson_title = row.get("lesson_title") or "Class"
        locator = row.get("locator") or {}
        resource_id = row.get("resource_id")
        if row.get("kind") == "objective":
            position = locator.get("position") or row.get("sequence_index")
            code = locator.get("code")
            label = f"{lesson_title} · ELO {position}" + (f" ({code})" if code else "")
        else:
            file_label = row.get("resource_label") or row.get("filename") or "Lesson file"
            label = " · ".join(
                part for part in (lesson_title, file_label, locator_label(locator)) if part
            )
        return RetrievedChunk(
            kind="lesson",
            label=label,
            text=row.get("text", ""),
            similarity=float(row.get("similarity", 0.0)),
            reader_link=build_lesson_link(row["lesson_id"], resource_id),
            locator={
                "lesson_id": row["lesson_id"],
                "resource_id": resource_id,
                "objective_id": row.get("objective_id"),
                **{key: value for key, value in locator.items() if key in ("slide", "page", "part", "position")},
            },
        )

    @staticmethod
    def _wiki_chunk(row: dict[str, Any]) -> RetrievedChunk:
        return RetrievedChunk(
            kind="wiki",
            label=row.get("preferred_label", "Definition"),
            text=row.get("definition", ""),
            similarity=float(row.get("similarity", 0.0)),
            reader_link=f"/app/wiki/{row.get('canonical_slug', '')}",
            locator={"wiki_entry_id": row["id"], "slug": row.get("canonical_slug")},
        )
