"""Export the curated wiki as a JSON artifact.

The wiki is knowledge the author curated while reading a source, so it is a
first-class Mathesys output: ``export-wiki-json`` snapshots every canonical
entry belonging to a source into one versioned JSON document that can be
downloaded, diffed, or re-imported like any other artifact.

Entry selection per source:
- entries whose ``evidence`` cites the source, or whose ``origin.source_id``
  records it (manual batches without evidence links) → scope ``source``;
- entries with no source affiliation at all (workspace-level quick adds)
  → included with scope ``workspace`` so curated knowledge is never silently
  missing from the export.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

EXPORT_FORMAT_VERSION = "1.0"


def _entry_scope(entry: dict[str, Any], source_id: str) -> str | None:
    """Return ``source``/``workspace`` scope, or ``None`` to exclude."""
    evidence = entry.get("evidence") or []
    origin = entry.get("origin") or {}

    cites_source = any(
        record.get("source_id") == source_id
        for record in evidence
        if isinstance(record, dict)
    )
    if cites_source or origin.get("source_id") == source_id:
        return "source"

    has_any_source = origin.get("source_id") or any(
        record.get("source_id")
        for record in evidence
        if isinstance(record, dict)
    )
    return None if has_any_source else "workspace"


def _export_entry(
    entry: dict[str, Any],
    *,
    scope: str,
    label_by_id: dict[str, str],
) -> dict[str, Any]:
    return {
        "id": str(entry["id"]),
        "preferred_label": entry.get("preferred_label"),
        "canonical_slug": entry.get("canonical_slug"),
        "entry_kind": entry.get("entry_kind"),
        "importance": entry.get("importance"),
        "definition": entry.get("definition"),
        "pronunciation": entry.get("pronunciation"),
        "aliases": entry.get("aliases") or [],
        # Labels, not ids — the export should read standalone.
        "prerequisites": [
            label_by_id[prereq_id]
            for prereq_id in entry.get("prerequisites") or []
            if prereq_id in label_by_id
        ],
        "evidence": [
            {
                "source_id": record.get("source_id"),
                "segment_id": record.get("segment_id"),
                "page": record.get("page"),
            }
            for record in entry.get("evidence") or []
            if isinstance(record, dict) and record.get("segment_id")
        ],
        "origin": entry.get("origin") or {},
        "scope": scope,
    }


def build_wiki_export(
    *,
    wiki_entries: list[dict[str, Any]],
    workspace_id: str,
    source_id: str,
    source_filename: str | None,
) -> dict[str, Any]:
    canonical = [entry for entry in wiki_entries if entry.get("status") == "canonical"]
    label_by_id = {
        str(entry["id"]): str(entry.get("preferred_label") or "")
        for entry in canonical
    }

    exported: list[dict[str, Any]] = []
    kind_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}

    for entry in canonical:
        scope = _entry_scope(entry, source_id)

        if scope is None:
            continue

        exported.append(_export_entry(entry, scope=scope, label_by_id=label_by_id))
        kind = str(entry.get("entry_kind") or "concept")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        scope_counts[scope] = scope_counts.get(scope, 0) + 1

    if not exported:
        raise RuntimeError(
            f"No canonical wiki entries found for source {source_id}. "
            "Run Wiki Knowledge from OPS, then open entries in Academy Library before exporting.",
        )

    exported.sort(
        key=lambda item: (
            str(item.get("entry_kind") or ""),
            str(item.get("preferred_label") or "").lower(),
        ),
    )

    return {
        "arsenal_wiki_export": EXPORT_FORMAT_VERSION,
        "workspace_id": workspace_id,
        "source_id": source_id,
        "source_filename": source_filename,
        "generated_at": datetime.now(UTC).isoformat(),
        "entry_count": len(exported),
        "entry_kind_counts": kind_counts,
        "scope_counts": scope_counts,
        "entries": exported,
    }
