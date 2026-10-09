"""Read a knowledge upload that is already structured wiki entries.

Accepted shapes:

- ``{"terms": [...], "key_lists": [...]}`` (notes export)
- ``{"entries": [ ... ], "unparsed_fragments": [ ... ]}`` (model output or a wiki export)
- a bare array of entries
- one entry object

A term needs a label and a definition. A list needs a label plus an overview
or at least one item. ``prerequisites`` (wiki export) is accepted as
``prerequisite_labels``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class StructuredNotesError(ValueError):
    """The text is JSON, but it is not usable wiki entries."""


@dataclass(frozen=True)
class StructuredNotes:
    entries: list[dict[str, Any]]
    unparsed_fragments: list[str]


def parse_structured_notes(text: str) -> StructuredNotes | None:
    """Return entries when ``text`` is structured JSON, else ``None``.

    Prose, and text that only looks like it might be JSON, returns ``None``
    so the structuring model can still read it. Valid JSON in the wrong shape
    raises ``StructuredNotesError``.
    """
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return _notes_from_payload(payload)


def require_structured_notes(text: str, *, filename: str) -> StructuredNotes:
    """Parse a ``.json`` upload. Invalid JSON or a missing entry is an error."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StructuredNotesError(f"Could not read '{filename}' as JSON.") from exc
    try:
        return _notes_from_payload(payload)
    except StructuredNotesError as exc:
        raise StructuredNotesError(f"{filename}: {exc}") from exc


def _notes_from_payload(payload: Any) -> StructuredNotes:
    if isinstance(payload, dict) and ("terms" in payload or "key_lists" in payload):
        return _notes_from_terms_and_lists(payload)

    fragments: list[Any]
    if isinstance(payload, list):
        raw_entries = payload
        fragments = []
    elif isinstance(payload, dict) and "entries" in payload:
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise StructuredNotesError("entries must be an array.")
        raw_fragments = payload.get("unparsed_fragments") or []
        fragments = raw_fragments if isinstance(raw_fragments, list) else []
    elif isinstance(payload, dict) and _label(payload) and (_definition(payload) or _items(payload)):
        raw_entries = [payload]
        fragments = []
    else:
        raise StructuredNotesError(
            "JSON needs an entries array, or terms and key_lists. "
            "Each term needs a label and a definition.",
        )

    entries = [normalized for raw in raw_entries if (normalized := _normalize_entry(raw))]
    if not entries:
        raise StructuredNotesError(
            "JSON needs at least one entry with a label and a definition.",
        )
    return StructuredNotes(
        entries=entries,
        unparsed_fragments=[str(fragment) for fragment in fragments if str(fragment).strip()],
    )


def _notes_from_terms_and_lists(payload: dict[str, Any]) -> StructuredNotes:
    raw_terms = payload.get("terms") or []
    raw_lists = payload.get("key_lists") or []
    if not isinstance(raw_terms, list) or not isinstance(raw_lists, list):
        raise StructuredNotesError("terms and key_lists must be arrays.")

    entries: list[dict[str, Any]] = []
    labels: set[str] = set()

    for raw in raw_terms:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("term") or raw.get("label") or raw.get("preferred_label") or "").strip()
        definition = str(raw.get("definition") or "").strip()
        if not label or not definition:
            continue
        entries.append(
            _entry(
                label=label,
                definition=definition,
                entry_kind="term",
                significance=_optional_text(raw.get("significance")),
                category=_optional_text(raw.get("category")),
                importance=str(raw.get("importance") or "supporting"),
            ),
        )
        labels.add(label.casefold())

    for raw in raw_lists:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("concept") or raw.get("label") or raw.get("preferred_label") or "").strip()
        if not label:
            continue
        items = _items(raw)
        category = _optional_text(raw.get("category"))
        for item in items:
            if item["name"].casefold() in labels or not item["details"]:
                continue
            entries.append(
                _entry(
                    label=item["name"],
                    definition=item["details"],
                    entry_kind="term",
                    category=category,
                ),
            )
            labels.add(item["name"].casefold())
        overview = str(raw.get("overview") or raw.get("definition") or "").strip()
        if not overview and not items:
            continue
        entries.append(
            _entry(
                label=label,
                definition=overview,
                entry_kind="list",
                category=category,
                items=items,
                importance=str(raw.get("importance") or "supporting"),
            ),
        )

    if not entries:
        raise StructuredNotesError(
            "JSON needs at least one term with a definition or one list with items.",
        )
    return StructuredNotes(entries=entries, unparsed_fragments=[])


def _normalize_entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    label = _label(raw)
    if not label:
        return None
    definition = _definition(raw)
    items = _items(raw)
    kind = _kind(raw)
    if kind == "list":
        if not definition and not items:
            return None
    elif not definition:
        return None
    prerequisites = raw.get("prerequisite_labels")
    if not isinstance(prerequisites, list):
        prerequisites = raw.get("prerequisites") if isinstance(raw.get("prerequisites"), list) else []
    aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
    pronunciation = raw.get("pronunciation")
    return _entry(
        label=label,
        definition=definition,
        entry_kind=kind,
        significance=_optional_text(raw.get("significance")),
        category=_optional_text(raw.get("category")),
        items=items,
        aliases=[str(alias) for alias in aliases if str(alias).strip()],
        pronunciation=str(pronunciation) if pronunciation else None,
        importance=str(raw.get("importance") or "supporting"),
        prerequisite_labels=[str(item) for item in prerequisites if str(item).strip()],
        note_excerpt=str(raw.get("note_excerpt") or ""),
    )


def _entry(
    *,
    label: str,
    definition: str,
    entry_kind: str,
    significance: str | None = None,
    category: str | None = None,
    items: list[dict[str, str]] | None = None,
    aliases: list[str] | None = None,
    pronunciation: str | None = None,
    importance: str = "supporting",
    prerequisite_labels: list[str] | None = None,
    note_excerpt: str = "",
) -> dict[str, Any]:
    return {
        "label": label,
        "definition": definition,
        "entry_kind": "list" if entry_kind == "list" else "term",
        "significance": significance,
        "category": category,
        "items": items or [],
        "aliases": aliases or [],
        "pronunciation": pronunciation,
        "importance": importance or "supporting",
        "prerequisite_labels": prerequisite_labels or [],
        "note_excerpt": note_excerpt,
    }


def _label(raw: dict[str, Any]) -> str:
    return str(raw.get("label") or raw.get("preferred_label") or "").strip()


def _definition(raw: dict[str, Any]) -> str:
    return str(raw.get("definition") or raw.get("overview") or "").strip()


def _kind(raw: dict[str, Any]) -> str:
    kind = str(raw.get("entry_kind") or "term").strip().lower()
    return "list" if kind == "list" else "term"


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _items(raw: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = raw.get("items")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for item in raw_items:
        if isinstance(item, str):
            name = item.strip()
            details = ""
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("label") or "").strip()
            details = str(item.get("details") or item.get("definition") or "").strip()
        else:
            continue
        if name:
            items.append({"name": name, "details": details})
    return items
