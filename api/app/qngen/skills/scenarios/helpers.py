# Scenario skill helpers — deterministic post-processing hooks.

from __future__ import annotations

from typing import Any


def filter_essential_only(
    items: list[dict[str, Any]],
    *,
    essential_wiki_ids: set[str],
) -> list[dict[str, Any]]:
    """Scenarios are generated only for essential concepts."""
    return [
        item
        for item in items
        if essential_wiki_ids.intersection(item.get("wiki_ids_cited") or [])
    ]


def ensure_list_scenarios(
    items: list[dict[str, Any]],
    concepts: list[Any],
    *,
    include_supporting: bool = False,
) -> list[dict[str, Any]]:
    """Add one decision that uses a list's components when the model skipped it."""
    cited = {
        str(wiki_id)
        for item in items
        for wiki_id in (item.get("wiki_ids_cited") or [])
    }
    extra: list[dict[str, Any]] = []
    for concept in concepts:
        if concept.entry_kind != "list" or concept.wiki_id in cited:
            continue
        if concept.importance != "essential" and not include_supporting:
            continue
        members = _member_lines(concept.items)
        if not members:
            continue
        names = [name for name, _details in members]
        situation = concept.definition.strip()
        roster = "\n".join(
            f"- {name}: {details}" if details else f"- {name}" for name, details in members
        )
        situation = f"{situation}\n\n{roster}".strip()
        extra.append(
            {
                "type": "scenario",
                "subtype": "decision_prompt",
                "difficulty": "medium",
                "wiki_ids_cited": [concept.wiki_id],
                "source_chunk_ids": list(concept.evidence_segment_ids[:1]),
                "title": concept.preferred_label,
                "situation": situation,
                "task": (
                    f"A decision in front of you turns on {concept.preferred_label}. "
                    "Choose which component should govern your action and say what you will do."
                ),
                "expected_response_elements": names,
                "rubric": {
                    "excellent": "Commits to one component and applies it to a concrete action.",
                    "satisfactory": "Names a relevant component without a clear action.",
                    "poor": "Ignores the components or refuses the decision.",
                },
            },
        )
        cited.add(concept.wiki_id)
    return [*items, *extra]


def _member_lines(items: list[Any]) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    for raw in items:
        if isinstance(raw, dict):
            name = str(raw.get("name") or "").strip()
            details = str(raw.get("details") or "").strip()
        else:
            name = str(raw).strip()
            details = ""
        if name:
            members.append((name, details))
    return members
