"""Generate Study Material components and plan section layouts.

Pure functions over injected clients so the worker owns persistence and the
tests own the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Protocol

from app.mathesys.study_material.catalog import Template, TemplateSection, Theme
from app.mathesys.study_material.diagram import (
    diagram_summary,
    parse_diagram_spec,
    render_diagram_svg,
)
from app.mathesys.study_material.images import ImageClient, ImageRequest
from app.mathesys.study_material.layout import SectionLayout, normalize_section_layout
from app.mathesys.study_material.prompts import (
    DIAGRAM_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    TEXT_SYSTEM_PROMPT,
    ComponentPromptContext,
    diagram_user_prompt,
    image_prompt,
    orchestrator_user_prompt,
    text_user_prompt,
)
from app.mathesys.study_material.sanitize import sanitize_fragment
from app.services.llm.base import LLMCompletionResult

WORDS_PER_SQ_IN = 11.0
VISUAL_SHARE = 0.4
MAX_VISUAL_SHARE = 0.7
MIN_WORD_BUDGET = 25
_SUPPORTED_RATIOS = {"1:1": 1.0, "3:2": 1.5, "2:3": 2 / 3, "4:3": 4 / 3, "3:4": 0.75, "16:9": 16 / 9, "9:16": 9 / 16}


class StudyMaterialGenerationError(RuntimeError):
    """A component could not be generated from the model's response."""


class JsonCompleter(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> LLMCompletionResult: ...


@dataclass
class GeneratedComponent:
    output: dict[str, Any]
    model: str
    provider: str
    token_usage: dict[str, int]
    settings: dict[str, Any]
    summary: str
    binary: bytes | None = None
    binary_mime: str | None = None
    extension: str | None = None


@dataclass
class LayoutComponent:
    id: str
    component_type: str
    summary: str
    aspect: float | None = None
    words: int | None = None


@dataclass
class LayoutPlan:
    sections: dict[str, SectionLayout]
    completion: LLMCompletionResult | None = None
    rationale: dict[str, str] = field(default_factory=dict)


def text_word_budget(template: Template, section: TemplateSection, *, visual_count: int, text_count: int) -> int:
    width_in, height_in = template.section_size_in(section)
    visual_share = min(MAX_VISUAL_SHARE, VISUAL_SHARE * visual_count)
    density = WORDS_PER_SQ_IN * (10.5 / template.body_pt) ** 2
    area = width_in * height_in * (1 - visual_share) / max(1, text_count)
    return max(MIN_WORD_BUDGET, int(area * density))


def auto_aspect_ratio(template: Template, section: TemplateSection, *, sibling_count: int) -> str:
    width_in, height_in = template.section_size_in(section)
    section_aspect = width_in / height_in if height_in else 1.0
    if sibling_count == 0:
        target = section_aspect
    elif section_aspect >= 1.4:
        target = (width_in * 0.5) / height_in
    else:
        target = width_in / (height_in * 0.45)
    return min(_SUPPORTED_RATIOS, key=lambda ratio: abs(_SUPPORTED_RATIOS[ratio] - target))


def orientation_label(aspect_ratio: str) -> str:
    value = _SUPPORTED_RATIOS.get(aspect_ratio, 1.0)
    if value > 1.05:
        return "landscape"
    if value < 0.95:
        return "portrait"
    return "square"


class _TextCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.words = 0

    def handle_data(self, data: str) -> None:
        self.words += len(data.split())


def count_words(html: str) -> int:
    counter = _TextCounter()
    counter.feed(html)
    counter.close()
    return counter.words


def generate_diagram_component(
    ctx: ComponentPromptContext,
    completer: JsonCompleter,
) -> GeneratedComponent:
    completion = completer.complete_json(
        system_prompt=DIAGRAM_SYSTEM_PROMPT,
        user_prompt=diagram_user_prompt(ctx),
    )
    spec = parse_diagram_spec(completion.content)
    rendered = render_diagram_svg(spec, ctx.theme.diagram)
    summary = diagram_summary(spec)
    return GeneratedComponent(
        output={
            "svg": rendered.svg,
            "aspect": rendered.aspect,
            "caption": spec.caption,
            "alt": spec.caption or summary,
            "spec": {
                "layout": spec.layout,
                "direction": spec.direction,
                "nodes": [
                    {"id": node.id, "label": node.label, "detail": node.detail, "emphasis": node.emphasis}
                    for node in spec.nodes
                ],
                "connections": [
                    {"from": edge.source, "to": edge.target, "label": edge.label} for edge in spec.edges
                ],
            },
        },
        model=completion.model,
        provider=completion.provider,
        token_usage=dict(completion.token_usage),
        settings={},
        summary=summary,
    )


def generate_text_component(
    ctx: ComponentPromptContext,
    completer: JsonCompleter,
) -> GeneratedComponent:
    completion = completer.complete_json(
        system_prompt=TEXT_SYSTEM_PROMPT,
        user_prompt=text_user_prompt(ctx),
    )
    raw_html = completion.content.get("html")
    if not isinstance(raw_html, str) or not raw_html.strip():
        raise StudyMaterialGenerationError("The text model returned no HTML.")
    html = sanitize_fragment(raw_html)
    if not html:
        raise StudyMaterialGenerationError("The text HTML was empty after sanitizing.")
    summary = " ".join(str(completion.content.get("summary") or "").split())[:240]
    words = count_words(html)
    return GeneratedComponent(
        output={"html": html, "summary": summary, "word_count": words, "word_budget": ctx.word_budget},
        model=completion.model,
        provider=completion.provider,
        token_usage=dict(completion.token_usage),
        settings={},
        summary=summary or f"{words} words of text",
    )


def _alt_text(instructions: str) -> str:
    first = re.split(r"(?<=[.!?])\s", " ".join(instructions.split()), maxsplit=1)[0]
    return first[:160] or "Instructional illustration"


def generate_image_component(
    ctx: ComponentPromptContext,
    client: ImageClient,
    *,
    aspect_ratio: str,
    quality: str,
    image_size: str,
    references: list[Any],
) -> GeneratedComponent:
    prompt = image_prompt(ctx, orientation=orientation_label(aspect_ratio))
    result = client.generate(
        ImageRequest(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            image_size=image_size,
            references=references,
        ),
    )
    alt = _alt_text(ctx.instructions)
    extension = "jpg" if result.mime_type == "image/jpeg" else result.mime_type.split("/")[-1]
    return GeneratedComponent(
        output={
            "mime_type": result.mime_type,
            "width": result.width,
            "height": result.height,
            "aspect": round(result.width / result.height, 4) if result.height else 1.0,
            "alt": alt,
            "prompt": prompt,
        },
        model=result.model,
        provider=result.provider,
        token_usage=result.token_usage,
        settings={**result.settings, "aspect_ratio": aspect_ratio},
        summary=f"image: {alt}",
        binary=result.data,
        binary_mime=result.mime_type,
        extension=extension,
    )


def plan_layout(
    *,
    title: str,
    theme: Theme,
    template: Template,
    components_by_section: dict[str, list[LayoutComponent]],
    section_notes: dict[str, str],
    completer: JsonCompleter | None,
) -> LayoutPlan:
    sections_payload: list[dict[str, Any]] = []
    for section in template.flexible_sections:
        components = components_by_section.get(section.id) or []
        if not components:
            continue
        width_in, height_in = template.section_size_in(section)
        sections_payload.append(
            {
                "section_id": section.id,
                "label": section.label,
                "size_in": [width_in, height_in],
                "layout_notes": section_notes.get(section.id) or "",
                "components": [
                    {
                        "id": item.id,
                        "type": item.component_type,
                        **({"aspect": item.aspect} if item.aspect else {}),
                        **({"words": item.words} if item.words is not None else {}),
                        "summary": item.summary[:200],
                    }
                    for item in components
                ],
            },
        )

    completion: LLMCompletionResult | None = None
    raw_by_section: dict[str, dict[str, Any]] = {}
    rationale: dict[str, str] = {}
    if completer is not None and sections_payload:
        completion = completer.complete_json(
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
            user_prompt=orchestrator_user_prompt(
                title=title,
                theme=theme,
                template=template,
                sections=sections_payload,
            ),
        )
        for item in completion.content.get("sections") or []:
            if isinstance(item, dict) and item.get("section_id"):
                raw_by_section[str(item["section_id"])] = item
                if item.get("rationale"):
                    rationale[str(item["section_id"])] = str(item["rationale"])[:240]

    layouts: dict[str, SectionLayout] = {}
    for section in template.flexible_sections:
        components = components_by_section.get(section.id) or []
        if not components:
            continue
        width_in, height_in = template.section_size_in(section)
        layouts[section.id] = normalize_section_layout(
            raw_by_section.get(section.id),
            [item.id for item in components],
            {item.id for item in components if item.component_type != "text"},
            section_aspect=width_in / height_in if height_in else 1.0,
        )
    return LayoutPlan(sections=layouts, completion=completion, rationale=rationale)
