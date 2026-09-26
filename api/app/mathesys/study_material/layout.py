"""Section layout plans: what the orchestrator may change, clamped by code.

The orchestrator can reorder, resize, align, space, and emphasize components
inside a section. It cannot move a component to another section, add one, or
drop one; normalization enforces that regardless of what the model returns.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

ARRANGEMENTS = frozenset({"stack", "row", "grid"})
ALIGNMENTS = frozenset({"start", "center"})
GAPS = frozenset({"tight", "normal", "loose"})
MIN_SIZE = 12
MAX_SIZE = 88
MIN_FONT_SCALE = 0.7
MAX_FONT_SCALE = 1.15


@dataclass
class SectionLayout:
    arrangement: str = "stack"
    order: list[str] = field(default_factory=list)
    # Percent of the section's main axis for visual components; flex weight for text.
    sizes: dict[str, int] = field(default_factory=dict)
    align: str = "start"
    gap: str = "normal"
    emphasis: str | None = None
    font_scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def default_section_layout(
    component_ids: list[str],
    visual_ids: set[str],
    *,
    section_aspect: float,
) -> SectionLayout:
    """Reasonable layout before (or without) the orchestrator's plan."""
    wide = section_aspect >= 1.4
    arrangement = "row" if wide and len(component_ids) == 2 else "stack"
    visuals_first = sorted(component_ids, key=lambda cid: 0 if cid in visual_ids else 1)
    sizes = {cid: 45 if arrangement == "stack" else 50 for cid in component_ids if cid in visual_ids}
    return SectionLayout(arrangement=arrangement, order=visuals_first, sizes=sizes)


def normalize_section_layout(
    raw: dict[str, Any] | None,
    component_ids: list[str],
    visual_ids: set[str],
    *,
    section_aspect: float,
) -> SectionLayout:
    fallback = default_section_layout(component_ids, visual_ids, section_aspect=section_aspect)
    if not raw:
        return fallback

    arrangement = str(raw.get("arrangement") or fallback.arrangement).lower()
    if arrangement not in ARRANGEMENTS:
        arrangement = fallback.arrangement
    if arrangement == "grid" and len(component_ids) < 3:
        arrangement = fallback.arrangement

    known = set(component_ids)
    order: list[str] = []
    for cid in raw.get("order") or []:
        cid = str(cid)
        if cid in known and cid not in order:
            order.append(cid)
    order.extend(cid for cid in fallback.order if cid not in order)

    sizes: dict[str, int] = {}
    raw_sizes = raw.get("sizes") if isinstance(raw.get("sizes"), dict) else {}
    for cid in component_ids:
        value = raw_sizes.get(cid)
        if isinstance(value, (int, float)):
            sizes[cid] = int(_clamp(float(value), MIN_SIZE, MAX_SIZE))
        elif cid in fallback.sizes:
            sizes[cid] = fallback.sizes[cid]

    # Visual shares on one axis cannot add up past the section.
    if arrangement in {"stack", "row"}:
        visual_total = sum(size for cid, size in sizes.items() if cid in visual_ids)
        has_text = any(cid not in visual_ids for cid in component_ids)
        budget = 70 if has_text else 100
        if visual_total > budget:
            factor = budget / visual_total
            for cid in list(sizes):
                if cid in visual_ids:
                    sizes[cid] = max(MIN_SIZE, int(sizes[cid] * factor))

    align = str(raw.get("align") or "start").lower()
    gap = str(raw.get("gap") or "normal").lower()
    emphasis = raw.get("emphasis")
    try:
        font_scale = float(raw.get("font_scale") or 1.0)
    except (TypeError, ValueError):
        font_scale = 1.0

    return SectionLayout(
        arrangement=arrangement,
        order=order,
        sizes=sizes,
        align=align if align in ALIGNMENTS else "start",
        gap=gap if gap in GAPS else "normal",
        emphasis=str(emphasis) if emphasis in known else None,
        font_scale=round(_clamp(font_scale, MIN_FONT_SCALE, MAX_FONT_SCALE), 3),
    )


def layout_from_stored(raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    sections = (raw or {}).get("sections")
    return sections if isinstance(sections, dict) else {}
