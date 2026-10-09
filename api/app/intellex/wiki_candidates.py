"""Producer-neutral wiki promotion.

A ``WikiCandidate`` is a fully-specified proposed wiki entry, independent of
where it came from (today: the manual authoring flow; formerly: extraction).
``promote_candidates`` turns a candidate set into insert/update payloads for
``wiki_entries`` while enforcing the workspace's slug-uniqueness and merge
semantics: aliases union, evidence records dedup on ``(source_id, segment_id)``,
importance keeps the higher tier, and a term and a list for the same label
stay on different slugs. Two lists union their items by name.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.intellex.wiki_slug import normalize_slug

Importance = Literal["essential", "supporting", "contextual"]
EntryKind = Literal["term", "list"]


def canonical_kind(entry_kind: str) -> EntryKind:
    """Map a stored or proposed kind onto ``term`` or ``list``.

    Older rows used ``concept`` and ``insight``. Both are terms.
    """
    return "list" if str(entry_kind or "").strip().lower() == "list" else "term"


def merge_group(entry_kind: str) -> str:
    """A term and a list with the same label are different entries."""
    return canonical_kind(entry_kind)


def pick_importance(existing: str, proposed: str) -> str:
    priority = {"essential": 3, "supporting": 2, "contextual": 1}
    return proposed if priority.get(proposed, 0) > priority.get(existing, 0) else existing


class WikiCandidate(BaseModel):
    label: str
    definition: str
    entry_kind: EntryKind = "term"
    significance: str | None = None
    category: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    prerequisite_labels: list[str] = Field(default_factory=list)
    pronunciation: str | None = None
    importance: Importance = "supporting"
    # Evidence records already in wiki_entries shape:
    # {"source_id": …, "segment_id": …, "page": …, "quote"?: …}
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    origin: dict[str, Any] = Field(default_factory=dict)

    @field_validator("entry_kind", mode="before")
    @classmethod
    def _coerce_kind(cls, value: object) -> EntryKind:
        return canonical_kind(str(value or "term"))

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, value: object) -> list[dict[str, Any]]:
        return normalize_items(value)


def candidate_slug(
    candidate: WikiCandidate,
    entries_by_slug: dict[str, dict[str, Any]],
) -> str:
    base = normalize_slug(candidate.label)
    existing = entries_by_slug.get(base)

    # A term and a list do not share a slug. The new row takes a kind suffix.
    if existing and merge_group(str(existing.get("entry_kind") or "term")) != merge_group(
        candidate.entry_kind
    ):
        return f"{base}--{candidate.entry_kind}"

    return base


def _normalize_definition(definition: str) -> str:
    return re.sub(r"\s+", " ", definition.strip().lower())


def definitions_conflict(existing: str, proposed: str) -> bool:
    if _normalize_definition(existing) == _normalize_definition(proposed):
        return False

    shorter, longer = sorted([existing, proposed], key=len)
    return shorter not in longer


def normalize_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in value:
        if isinstance(raw, str):
            name = raw.strip()
            details = ""
        elif isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("label") or "").strip()
            details = str(raw.get("details") or raw.get("definition") or "").strip()
        else:
            continue
        if name:
            items.append({"name": name, "details": details})
    return items


def merge_items(
    existing: list[dict[str, Any]] | None,
    proposed: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Keep existing order, then append names that are not already present."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in normalize_items(existing) + normalize_items(proposed):
        key = item["name"].casefold()
        if key in seen:
            continue
        merged.append(item)
        seen.add(key)
    return merged


def _optional_text(existing: object, proposed: object, *, replace: bool) -> str | None:
    existing_text = str(existing or "").strip() or None
    proposed_text = str(proposed or "").strip() or None
    if replace and proposed_text:
        return proposed_text
    return existing_text or proposed_text


def entry_embedding_text(
    label: str,
    definition: str,
    *,
    significance: object = None,
    items: object = None,
) -> str:
    parts = [label.strip(), definition.strip(), str(significance or "").strip()]
    for item in normalize_items(items):
        parts.append(item["name"])
        if item["details"]:
            parts.append(item["details"])
    return ". ".join(part for part in parts if part)


def merge_evidence(
    existing: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen = {
        (item.get("source_id"), item.get("segment_id"))
        for item in existing
    }
    merged = list(existing)

    for item in new_items:
        key = (item.get("source_id"), item.get("segment_id"))

        if key in seen:
            continue

        merged.append(item)
        seen.add(key)

    return merged


def promote_candidates(
    *,
    workspace_id: str,
    candidates: list[WikiCandidate],
    existing_entries: list[dict[str, Any]],
    override_conflicts: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[int]]:
    """Return wiki rows to insert, wiki rows to update, and conflicted indexes.

    ``override_conflicts=False`` leaves conflicting candidates untouched and
    reports their indexes so the caller can surface them; ``True`` applies the
    candidate's definition over the existing one (the reviewed human choice
    wins — the manual flow's dispute resolution).
    """
    entries_by_slug = {
        str(entry["canonical_slug"]): entry
        for entry in existing_entries
    }
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    conflicted: list[int] = []

    for index, candidate in enumerate(candidates):
        slug = candidate_slug(candidate, entries_by_slug)
        existing = entries_by_slug.get(slug)

        if not existing:
            row = {
                "workspace_id": workspace_id,
                "preferred_label": candidate.label,
                "canonical_slug": slug,
                "definition": candidate.definition,
                "significance": candidate.significance,
                "category": candidate.category,
                "items": candidate.items,
                "pronunciation": candidate.pronunciation,
                "aliases": candidate.aliases,
                "prerequisites": [],
                "importance": candidate.importance,
                "entry_kind": candidate.entry_kind,
                "status": "canonical",
                "evidence": candidate.evidence,
                "origin": candidate.origin,
            }
            inserts.append(row)
            entries_by_slug[slug] = row
            continue

        conflict = definitions_conflict(
            str(existing.get("definition") or ""),
            candidate.definition,
        )

        if conflict and not override_conflicts:
            conflicted.append(index)
            continue

        merged_aliases = sorted(
            {
                *(existing.get("aliases") or []),
                *candidate.aliases,
                candidate.label,
            }
            - {str(existing.get("preferred_label") or "")},
        )
        replace_text = conflict and override_conflicts
        updates.append(
            {
                "id": existing["id"],
                "definition": (
                    candidate.definition
                    if conflict
                    else existing.get("definition") or candidate.definition
                ),
                "significance": _optional_text(
                    existing.get("significance"),
                    candidate.significance,
                    replace=replace_text,
                ),
                "category": _optional_text(
                    existing.get("category"),
                    candidate.category,
                    replace=replace_text,
                ),
                "items": merge_items(existing.get("items"), candidate.items),
                "pronunciation": existing.get("pronunciation") or candidate.pronunciation,
                "aliases": merged_aliases,
                "importance": pick_importance(
                    str(existing.get("importance") or "supporting"),
                    candidate.importance,
                ),
                "entry_kind": canonical_kind(str(existing.get("entry_kind") or candidate.entry_kind)),
                "status": "canonical",
                "evidence": merge_evidence(existing.get("evidence") or [], candidate.evidence),
                "origin": candidate.origin,
            },
        )

    return inserts, updates, conflicted


def resolve_prerequisites(
    *,
    candidates: list[WikiCandidate],
    wiki_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map candidate ``prerequisite_labels`` to wiki ids across the workspace.

    Labels that match nothing are dropped silently — a prerequisite the author
    named but never curated is not an error.
    """
    label_to_id: dict[str, str] = {}

    for row in wiki_rows:
        label_to_id[normalize_slug(str(row["preferred_label"]))] = str(row["id"])

        for alias in row.get("aliases") or []:
            label_to_id[normalize_slug(str(alias))] = str(row["id"])

    updates: list[dict[str, Any]] = []

    for row in wiki_rows:
        slug = str(row["canonical_slug"])
        matching = [
            candidate
            for candidate in candidates
            if normalize_slug(candidate.label) == slug
        ]

        if not matching:
            continue

        prerequisite_ids: list[str] = []

        for label in matching[0].prerequisite_labels:
            wiki_id = label_to_id.get(normalize_slug(label))

            if wiki_id and wiki_id != row.get("id"):
                prerequisite_ids.append(wiki_id)

        if prerequisite_ids:
            updates.append(
                {
                    "id": row["id"],
                    "prerequisites": sorted(set(prerequisite_ids)),
                },
            )

    return updates
