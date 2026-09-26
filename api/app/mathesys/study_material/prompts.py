"""Prompts for Study Material component generation and layout orchestration.

Every call receives the artifact context it needs (title, theme guidance,
template and section constraints, sibling components, user instructions,
reference files). Nothing relies on model memory between calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.mathesys.study_material.catalog import Template, TemplateSection, Theme

TEXT_SYSTEM_PROMPT = """You write one Text component for a printed, single-page study material.

Return JSON only: {"html": "<p>...</p>", "summary": "one sentence describing what the text covers"}

HTML rules:
- Tags allowed: section, div, p, h2, h3, h4, ul, ol, li, dl, dt, dd, table, thead, tbody, tr, th, td, strong, em, b, i, blockquote, hr, br, small, code, sup, sub, span.
- Classes allowed (structure only; the theme styles them): callout, caption, cols-2, compare, definition, formula, key-term, kicker, label, lead, list-compact, question, steps, takeaways.
- No inline styles, images, SVG, scripts, links, or h1. The template already prints the artifact title.

Content rules:
- Choose the structure that fits the content: short paragraphs, bullets, numbered steps (ol.steps), definitions (dl), key terms, a comparison table, questions, key takeaways (div.takeaways), captions, or labels.
- Stay inside the word budget. Printed space is fixed; words past the budget get shrunk or cut.
- Facts must come from the instructions and reference material. Do not invent statistics, quotes, citations, dates, or publication numbers.
- Write for the reader of the page. No meta commentary, no "this section covers".
- Visuals already exist in this section. Complement them instead of restating them, and never refer to them by position (no "above", "left", "below").
"""

DIAGRAM_SYSTEM_PROMPT = """You design one diagram for a printed study material. Code positions and draws everything; you only describe structure.

Return JSON only:
{"caption": "optional caption, 12 words max, or empty string",
 "layout": "flow" | "hierarchy" | "cycle",
 "direction": "TB" | "LR",
 "nodes": [{"id": "n1", "label": "6 words max", "detail": "optional, 12 words max", "emphasis": false}],
 "connections": [{"from": "n1", "to": "n2", "label": "optional, 3 words max"}]}

Rules:
- 3 to 12 nodes. Never give coordinates, sizes, or colors.
- "flow" for processes and sequences, "hierarchy" for breakdowns and trees, "cycle" only for loops that return to the start.
- Use "LR" only when the region is wide and chains are short (5 nodes or fewer); otherwise "TB".
- At most one node has "emphasis": true, the single most important idea.
- Labels in sentence case. Facts come from the instructions and reference material only.
"""

ORCHESTRATOR_SYSTEM_PROMPT = """You are the layout orchestrator for a printed, single-page study material. You arrange components that already exist inside fixed template sections.

Return JSON only:
{"sections": [{"section_id": "...", "arrangement": "stack" | "row" | "grid",
  "order": ["component ids in reading order"],
  "sizes": {"component_id": number},
  "align": "start" | "center", "gap": "tight" | "normal" | "loose",
  "emphasis": "component id or null", "rationale": "one sentence"}]}

Rules:
- Use only the section ids and component ids given. Never move a component to another section, never drop or add one. List every component of a section exactly once in "order".
- "stack" is vertical, "row" is side by side, "grid" is two columns (three or more components only).
- For diagram and image components, "sizes" is the percent (12 to 88) of the section's main axis they occupy: height for stack, width for row. For text components it is a relative weight from 1 to 5 for the remaining space.
- Size visuals from their aspect ratio: a wide visual in a stack needs less height; a tall visual suits a row. Keep diagram labels legible.
- Leave text enough room for its word count at the template's body size. Estimate about 11 words per square inch.
- At most one emphasized component per section: the key takeaway.
- Follow the user's layout notes for a section when present, within these rules.
"""


@dataclass
class SiblingSummary:
    component_id: str
    component_type: str
    summary: str


@dataclass
class ComponentPromptContext:
    title: str
    theme: Theme
    template: Template
    section: TemplateSection
    instructions: str
    reference_text: str = ""
    siblings: list[SiblingSummary] = field(default_factory=list)
    word_budget: int | None = None
    section_notes: str = ""


def _section_line(ctx: ComponentPromptContext) -> str:
    width_in, height_in = ctx.template.section_size_in(ctx.section)
    return f"{ctx.section.label}: {width_in} × {height_in} in"


def _siblings_block(siblings: list[SiblingSummary]) -> str:
    if not siblings:
        return "None. This component has the section to itself."
    return "\n".join(f"- {item.component_type} ({item.component_id}): {item.summary}" for item in siblings)


def _reference_block(text: str) -> str:
    return text.strip() or "None supplied. Use only widely accepted, verifiable facts implied by the instructions."


def text_user_prompt(ctx: ComponentPromptContext) -> str:
    budget = ctx.word_budget or 120
    return f"""Artifact title: {ctx.title}
Template: {ctx.template.name} ({ctx.template.orientation}, {ctx.template.width_in} × {ctx.template.height_in} in, body text {ctx.template.body_pt}pt)
Theme: {ctx.theme.name}. {ctx.theme.guidance.get('typography', '')}
Section: {_section_line(ctx)}
Word budget: about {budget} words (hard maximum {round(budget * 1.15)}).

Other components in this section:
{_siblings_block(ctx.siblings)}

Section layout notes from the author: {ctx.section_notes or 'None.'}

Component instructions:
{ctx.instructions.strip() or 'Summarize the reference material for this section.'}

Reference material:
{_reference_block(ctx.reference_text)}
"""


def diagram_user_prompt(ctx: ComponentPromptContext) -> str:
    return f"""Artifact title: {ctx.title}
Theme diagram guidance: {ctx.theme.guidance.get('diagram', '')}
Section: {_section_line(ctx)}

Other components in this section:
{_siblings_block(ctx.siblings)}

Component instructions:
{ctx.instructions.strip() or 'Diagram the core structure of the reference material.'}

Reference material:
{_reference_block(ctx.reference_text)}
"""


def image_prompt(ctx: ComponentPromptContext, *, orientation: str) -> str:
    excerpt = ctx.reference_text.strip()[:2000]
    context = f"\nSupporting context:\n{excerpt}" if excerpt else ""
    return (
        f"{ctx.instructions.strip() or 'An instructional illustration for this study material.'}\n\n"
        f"Style: {ctx.theme.guidance.get('illustration', '')}\n"
        f"Composition: {orientation} image for a {_section_line(ctx)} region of a printed study sheet "
        f"titled \"{ctx.title}\". One clear subject, generous whitespace, prints well on white paper. "
        "No text, letters, numbers, labels, watermarks, logos, insignia, or seals."
        f"{context}"
    )


def orchestrator_user_prompt(
    *,
    title: str,
    theme: Theme,
    template: Template,
    sections: list[dict[str, Any]],
) -> str:
    return (
        f"Artifact title: {title}\n"
        f"Template: {template.name}, body text {template.body_pt}pt\n"
        f"Theme: {theme.name}\n\n"
        "Sections and their components:\n"
        f"{json.dumps(sections, indent=2)}\n"
    )
