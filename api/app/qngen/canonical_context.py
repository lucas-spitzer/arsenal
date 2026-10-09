from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import get_settings
from app.intellex.ndr_formatting import format_segments_for_llm

Importance = Literal["essential", "supporting", "contextual"]

_IMPORTANCE_ORDER = {"essential": 0, "supporting": 1, "contextual": 2}


class ConceptCard(BaseModel):
    wiki_id: str
    preferred_label: str
    definition: str
    entry_kind: str = "term"
    significance: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    pronunciation: str | None = None
    importance: Importance = "supporting"
    prerequisite_labels: list[str] = Field(default_factory=list)
    evidence_segment_ids: list[str] = Field(default_factory=list)
    evidence_segments: list[dict[str, Any]] = Field(default_factory=list)


def _evidence_for_source(
    evidence: list[dict[str, Any]] | None,
    source_id: str,
) -> list[dict[str, Any]]:
    if not evidence:
        return []

    return [
        record
        for record in evidence
        if record.get("source_id") == source_id and record.get("segment_id")
    ]


def build_source_concepts(
    *,
    wiki_entries: list[dict[str, Any]],
    source_id: str,
    segments: list[dict[str, Any]],
) -> list[ConceptCard]:
    segment_index = {str(segment["id"]): segment for segment in segments}
    wiki_by_id = {str(entry["id"]): entry for entry in wiki_entries}
    concepts: list[ConceptCard] = []

    for entry in wiki_entries:
        if entry.get("status") != "canonical":
            continue

        source_evidence = _evidence_for_source(entry.get("evidence"), source_id)
        if not source_evidence:
            continue

        segment_ids = [str(record["segment_id"]) for record in source_evidence]
        resolved_segments: list[dict[str, Any]] = []

        for segment_id in segment_ids:
            segment = segment_index.get(segment_id)
            if not segment:
                continue

            quote = None
            for record in source_evidence:
                if str(record.get("segment_id")) == segment_id and record.get("quote"):
                    quote = str(record["quote"])
                    break

            segment_payload: dict[str, Any] = {
                "segment_id": segment_id,
                "kind": segment.get("kind"),
                "text": segment.get("text"),
                "page": (segment.get("locator") or {}).get("page"),
            }
            if quote:
                segment_payload["quote"] = quote
            resolved_segments.append(segment_payload)

        if not resolved_segments:
            continue

        prerequisite_ids = entry.get("prerequisites") or []
        prerequisite_labels = [
            str(wiki_by_id[prereq_id]["preferred_label"])
            for prereq_id in prerequisite_ids
            if prereq_id in wiki_by_id
        ]

        concepts.append(
            ConceptCard(
                wiki_id=str(entry["id"]),
                preferred_label=str(entry.get("preferred_label") or ""),
                definition=str(entry.get("definition") or ""),
                entry_kind=str(entry.get("entry_kind") or "term"),
                significance=(str(entry.get("significance")).strip() or None)
                if entry.get("significance")
                else None,
                items=entry.get("items") if isinstance(entry.get("items"), list) else [],
                aliases=[str(alias) for alias in (entry.get("aliases") or [])],
                pronunciation=entry.get("pronunciation"),
                importance=entry.get("importance") or "supporting",
                prerequisite_labels=prerequisite_labels,
                evidence_segment_ids=segment_ids,
                evidence_segments=resolved_segments,
            ),
        )

    concepts.sort(
        key=lambda concept: (
            _IMPORTANCE_ORDER.get(concept.importance, 99),
            concept.preferred_label.lower(),
        ),
    )
    return concepts


def batch_concepts(
    concepts: list[ConceptCard],
    *,
    batch_size: int | None = None,
) -> list[list[ConceptCard]]:
    if not concepts:
        return []

    resolved_batch_size = batch_size or get_settings().qngen.concept_batch_size
    batches: list[list[ConceptCard]] = []

    for start in range(0, len(concepts), resolved_batch_size):
        batches.append(concepts[start : start + resolved_batch_size])

    return batches


class ObjectiveBlueprint(BaseModel):
    objective_id: str
    statement: str
    bloom_level: str = "understand"
    concept_labels: list[str] = Field(default_factory=list)


class ChapterBlueprint(BaseModel):
    chapter_id: str
    chapter_title: str
    sequence_index: int
    segment_ids: list[str] = Field(default_factory=list)
    concepts: list[ConceptCard] = Field(default_factory=list)
    objectives: list[ObjectiveBlueprint] = Field(default_factory=list)


def chapters_from_document_chapters(
    chapter_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Blueprint chapter blocks from the persisted ``document_chapters`` table.

    Replaces the ``source_metadata["extract"]["chapters"]`` block the retired
    extraction stage used to persist: chapter structure now comes straight from
    the structuring/chunk stages. Objectives are empty — with a manually
    curated wiki, questions key off curated concepts grouped by chapter rather
    than extracted objectives.
    """
    chapters: list[dict[str, Any]] = []

    for row in chapter_rows:
        chapters.append(
            {
                "chapter_id": str(row.get("id") or ""),
                "chapter_title": str(row.get("title") or "Untitled"),
                "sequence_index": int(row.get("sequence_index") or 0),
                "segment_ids": [
                    str(segment_id) for segment_id in row.get("segment_ids") or []
                ],
                "objectives": [],
            },
        )

    return chapters


def build_chapter_blueprint(
    chapters: list[dict[str, Any]],
    concepts: list[ConceptCard],
) -> list[ChapterBlueprint]:
    """Join persisted chapter structure with this source's concepts.

    ``chapters`` is the block produced by ``chapters_from_document_chapters``.
    Each concept is attached to every chapter whose ``segment_ids`` overlap its
    evidence. Returns chapters ordered by ``sequence_index``.

    A concept may appear under more than one chapter when its evidence spans
    them; concepts with no overlapping chapter are simply absent (callers fall
    back to flat batching). Returns an empty list when no chapter structure is
    available, keeping the concept-fan-out path intact.
    """
    if not chapters:
        return []

    blueprints: list[ChapterBlueprint] = []

    for chapter in chapters:
        segment_ids = [str(segment_id) for segment_id in (chapter.get("segment_ids") or [])]
        segment_set = set(segment_ids)

        chapter_concepts = [
            concept
            for concept in concepts
            if segment_set.intersection(concept.evidence_segment_ids)
        ]

        objectives = [
            ObjectiveBlueprint(
                objective_id=str(objective.get("objective_id") or ""),
                statement=str(objective.get("statement") or ""),
                bloom_level=str(objective.get("bloom_level") or "understand"),
                concept_labels=[
                    str(label) for label in (objective.get("concept_labels") or [])
                ],
            )
            for objective in chapter.get("objectives") or []
        ]

        blueprints.append(
            ChapterBlueprint(
                chapter_id=str(chapter.get("chapter_id") or ""),
                chapter_title=str(chapter.get("chapter_title") or "Untitled"),
                sequence_index=int(chapter.get("sequence_index") or 0),
                segment_ids=segment_ids,
                concepts=chapter_concepts,
                objectives=objectives,
            ),
        )

    blueprints.sort(key=lambda chapter: chapter.sequence_index)
    return blueprints


def format_concepts_for_llm(concepts: list[ConceptCard]) -> str:
    payload = [
        {
            "wiki_id": concept.wiki_id,
            "preferred_label": concept.preferred_label,
            "entry_kind": concept.entry_kind,
            "definition": concept.definition,
            "significance": concept.significance,
            "items": concept.items,
            "aliases": concept.aliases,
            "pronunciation": concept.pronunciation,
            "importance": concept.importance,
            "prerequisite_labels": concept.prerequisite_labels,
            "evidence_segments": concept.evidence_segments,
        }
        for concept in concepts
    ]
    return json.dumps(payload, indent=2)


def format_concept_segments_for_llm(concepts: list[ConceptCard]) -> str:
    segments: list[dict[str, Any]] = []
    seen_segment_ids: set[str] = set()

    for concept in concepts:
        for segment in concept.evidence_segments:
            segment_id = str(segment.get("segment_id"))
            if segment_id in seen_segment_ids:
                continue
            seen_segment_ids.add(segment_id)
            segments.append(segment)

    return format_segments_for_llm(
        [
            {
                "id": segment["segment_id"],
                "kind": segment.get("kind"),
                "text": segment.get("text"),
                "locator": {"page": segment.get("page")},
            }
            for segment in segments
        ],
    )
