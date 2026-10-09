from __future__ import annotations

import json
from typing import Any


def build_wiki_context(wiki_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "wiki_id": entry.get("id"),
            "preferred_label": entry.get("preferred_label"),
            "entry_kind": entry.get("entry_kind") or "term",
            "definition": entry.get("definition"),
            "significance": entry.get("significance"),
            "items": entry.get("items") or [],
            "pronunciation": entry.get("pronunciation"),
            "aliases": entry.get("aliases") or [],
        }
        for entry in wiki_entries
        if entry.get("status") == "canonical"
    ]


def compact_segments(segments: list[dict[str, Any]], *, limit: int = 60) -> list[dict[str, Any]]:
    sampled = segments[:limit]

    return [
        {
            "segment_id": segment.get("id"),
            "kind": segment.get("kind"),
            "text": segment.get("text"),
            "page": (segment.get("locator") or {}).get("page"),
        }
        for segment in sampled
    ]


def format_json_block(value: Any) -> str:
    return json.dumps(value, indent=2)
