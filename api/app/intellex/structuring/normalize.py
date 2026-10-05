"""Stage: NORMALIZE (llamaparse-normalize).

Flatten LlamaParse's structured `pages[].items[]` output into a single flat,
reading-order list of Elements, dropping page furniture (running headers and
footers / page numbers). A header or footer whose text is a chapter or part
label is kept and retyped as a heading, because some books set "CHAPTER ONE"
as a small kicker above the real title. Replaces the clutter-removal half of
the old prepare-document step, but does it structurally (by item type) rather
than with heuristics + an LLM call.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from app.intellex.structuring.boundaries import is_division_label
from app.intellex.structuring.models import FURNITURE_TYPES, Element


def _clean_text(item: dict[str, Any]) -> str:
    """Cleanest plain-text form of an item: LlamaParse `value`, else stripped md."""
    value = item.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    md = item.get("md") or ""
    md = re.sub(r"^\s*#{1,6}\s*", "", md)  # drop leading "# " / "## "
    return md.strip()


def _layout_provenance(
    item: dict[str, Any],
) -> tuple[tuple[str, ...], float | None, float | None, int]:
    """Return compact semantic evidence from an item's bbox fragments."""
    raw_boxes = item.get("bbox")
    if not isinstance(raw_boxes, list):
        return (), None, None, 0

    boxes = [box for box in raw_boxes if isinstance(box, dict)]
    labels = tuple(
        sorted(
            {
                label.strip().lower()
                for box in boxes
                if isinstance((label := box.get("label")), str) and label.strip()
            }
        )
    )
    confidences = [
        float(confidence)
        for box in boxes
        if isinstance((confidence := box.get("confidence")), (int, float))
        and not isinstance(confidence, bool)
    ]
    return (
        labels,
        min(confidences) if confidences else None,
        max(confidences) if confidences else None,
        len(boxes),
    )


def normalize_structured_pages(
    pages: Iterable[dict[str, Any]],
    *,
    furniture_types: tuple[str, ...] = FURNITURE_TYPES,
) -> tuple[list[Element], dict[str, int]]:
    """Return (elements, dropped_furniture_counts).

    `pages` is the LlamaParse structured result: a list of objects each with a
    `page_number` and an `items` list of {type, md, value, level, bbox, ...}.
    """
    furniture = set(furniture_types)
    elements: list[Element] = []
    dropped: dict[str, int] = {}
    index = 0

    for page in pages:
        page_no = page.get("page_number")
        for item in page.get("items", []):
            itype = item.get("type")
            text = _clean_text(item)
            # Chapter kickers are often small running-header lines ("CHAPTER ONE"
            # under the page number). Keep those as headings; still drop titles
            # and page numbers.
            if itype in furniture and not is_division_label(text):
                dropped[itype] = dropped.get(itype, 0) + 1
                continue
            if itype in furniture:
                itype = "heading"
            labels, min_confidence, max_confidence, fragment_count = (
                _layout_provenance(item)
            )
            elements.append(
                Element(
                    index=index,
                    page=page_no,
                    type=itype,
                    level=item.get("level"),
                    text=text,
                    md=item.get("md") or "",
                    layout_labels=labels,
                    min_layout_confidence=min_confidence,
                    max_layout_confidence=max_confidence,
                    layout_fragment_count=fragment_count,
                )
            )
            index += 1

    return elements, dropped
