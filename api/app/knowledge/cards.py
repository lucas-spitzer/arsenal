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


def card_description(entry: dict[str, Any]) -> str:
    definition = str(entry.get("definition") or "").strip()
    significance = str(entry.get("significance") or "").strip()
    if definition and significance:
        return f"{definition}\n\n{significance}"
    return definition or significance


def flashcard_sides(entry: dict[str, Any], layout: str) -> tuple[str, str]:
    """Return ``(front, back)`` text for a layout.

    An image layout still stores the label as the front text so the picture
    has alt text. The academy shows the image instead of that text.
    """
    label = str(entry.get("preferred_label") or "").strip()
    if layout == "image_label":
        return label, label
    return label, card_description(entry)


def layout_needs_image(layout: str) -> bool:
    return layout in PLACEMENT_FOR_LAYOUT


def entry_category(entry: dict[str, Any]) -> str:
    return str(entry.get("category") or "").strip() or "Uncategorized"


def entries_in_category(entries: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    wanted = category.strip() or "Uncategorized"
    return [entry for entry in entries if entry_category(entry) == wanted]
