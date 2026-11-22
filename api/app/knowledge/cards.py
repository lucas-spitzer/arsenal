"""Flashcard faces and category batches built from wiki entries."""

from __future__ import annotations

from typing import Any

LAYOUTS = ("label_description", "image_label", "image_label_description")
QUESTION_FORMATS = ("multiple_choice", "true_false_correction", "multiple_select")
SCENARIO_FORMATS = ("decision_prompt", "rubric_response")

# Academy reads this placement. ``front_with_label`` is image plus the label
# on the front, and the description on the back.
PLACEMENT_FOR_LAYOUT = {
    "image_label": "front",
    "image_label_description": "front_with_label",
}


def list_card_back(entry: dict[str, Any]) -> str:
    """Numbered item names for a list card. Details and the overview stay off.

    A list with no names falls back to the overview so the back is not empty.
    """
    names: list[str] = []
    for item in entry.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    if not names:
        return str(entry.get("definition") or "").strip()
    return "\n".join(f"{index}. {name}" for index, name in enumerate(names, start=1))


def compare_card_back(entry: dict[str, Any]) -> str:
    """One line per diff: dimension — a: … · b: …"""
    poles = [str(alias).strip() for alias in entry.get("aliases") or [] if str(alias).strip()]
    left = poles[0] if len(poles) >= 1 else "A"
    right = poles[1] if len(poles) >= 2 else "B"
    lines: list[str] = []
    for item in entry.get("items") or []:
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("name") or "").strip()
        a_text = str(item.get("a") or "").strip()
        b_text = str(item.get("b") or "").strip()
        if not dimension or not a_text or not b_text:
            continue
        lines.append(f"{dimension} — {left}: {a_text} · {right}: {b_text}")
    if lines:
        return "\n".join(lines)
    return str(entry.get("definition") or "").strip()


def definition_card_back(entry: dict[str, Any]) -> str:
    """Definition for a term. A list uses its numbered item names.

    An abbreviation shows the expanded title, then the definition.
    A compare shows each axis with both poles.
    """
    kind = str(entry.get("entry_kind") or "")
    if kind == "list":
        return list_card_back(entry)
    if kind == "compare":
        return compare_card_back(entry)
    definition = str(entry.get("definition") or "").strip()
    if kind == "abbreviation":
        title = str(entry.get("significance") or "").strip()
        if title and definition:
            return f"{title}\n{definition}"
        return title or definition
    return definition


def definition_flashcard_row(project: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    label = str(entry.get("preferred_label") or "").strip()
    return {
        "workspace_id": project["workspace_id"],
        "source_id": project["source_id"],
        "knowledge_project_id": str(project["id"]),
        "front": label,
        "back": definition_card_back(entry),
        "difficulty": "medium",
        "tags": [str(entry["category"])] if entry.get("category") else [],
        "citations": [{"uri": f"wiki://{entry['id']}", "type": "wiki"}],
        "visual": None,
        "origin": {"source": "wiki_definition"},
        "subtype": "basic",
    }


def is_definition_flashcard(row: dict[str, Any]) -> bool:
    origin = row.get("origin")
    return isinstance(origin, dict) and origin.get("source") == "wiki_definition"


def flashcard_sides(entry: dict[str, Any], layout: str) -> tuple[str, str]:
    """Return ``(front, back)`` text for a layout.

    An image layout still stores the label as the front text so the picture
    has alt text. The academy shows the image instead of that text.
    A term back is the definition. Significance stays on the entry until it is added to the card.
    """
    label = str(entry.get("preferred_label") or "").strip()
    if layout == "image_label":
        return label, label
    return label, definition_card_back(entry)


def layout_needs_image(layout: str) -> bool:
    return layout in PLACEMENT_FOR_LAYOUT


def entry_category(entry: dict[str, Any]) -> str:
    return str(entry.get("category") or "").strip() or "Uncategorized"


def entries_in_category(entries: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    wanted = category.strip() or "Uncategorized"
    return [entry for entry in entries if entry_category(entry) == wanted]
