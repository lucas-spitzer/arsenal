# Quiz skill helpers — deterministic post-processing hooks.

from __future__ import annotations

from typing import Any

from app.qngen.skills.shared.item_mapping import normalize_question_type


def normalize_quiz_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for item in items:
        row = dict(item)
        subtype = row.get("subtype") or "multiple_choice"
        row["subtype"] = subtype
        row["question_type"] = normalize_question_type(subtype)
        normalized.append(row)

    return normalized


def ensure_list_questions(
    items: list[dict[str, Any]],
    concepts: list[Any],
) -> list[dict[str, Any]]:
    """Ask for a list's members when the model never cited that list."""
    cited = {
        str(wiki_id)
        for item in items
        for wiki_id in (item.get("wiki_ids_cited") or [])
    }
    extra: list[dict[str, Any]] = []
    for concept in concepts:
        if concept.entry_kind != "list" or concept.wiki_id in cited:
            continue
        names = _member_names(concept.items)
        if not names:
            continue
        extra.append(
            {
                "type": "quiz",
                "subtype": "short_answer",
                "difficulty": "easy",
                "wiki_ids_cited": [concept.wiki_id],
                "source_chunk_ids": list(concept.evidence_segment_ids[:1]),
                "question": f"Name the members of {concept.preferred_label}.",
                "choices": [],
                "correct_answer": "; ".join(names),
                "explanation": concept.definition.strip()
                or f"{concept.preferred_label} includes {', '.join(names)}.",
            },
        )
        cited.add(concept.wiki_id)
    return [*items, *extra]


def _member_names(items: list[Any]) -> list[str]:
    names: list[str] = []
    for raw in items:
        if isinstance(raw, dict):
            name = str(raw.get("name") or "").strip()
        else:
            name = str(raw).strip()
        if name:
            names.append(name)
    return names
