"""Predefined themes and templates for Study Material.

Templates own page geometry and section rules. Themes own typography, color,
logos, the disclaimer, and the style guidance passed into generation calls.
Both are JSON files in this package so neither can be invented at runtime.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_DIR = Path(__file__).resolve().parent
ASSETS_DIR = CATALOG_DIR / "assets"

COMPONENT_TYPES: tuple[str, ...] = ("text", "diagram", "image")
STRICT_CONTENT = frozenset({"title", "logo", "footer"})
DISCLAIMER_PLACEMENTS = frozenset({"footer", "per_section"})


class CatalogError(ValueError):
    """A theme, template, or option does not exist or breaks catalog rules."""


@dataclass(frozen=True)
class Box:
    """Percent of the page's safe area (inside the template margin)."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class TemplateSection:
    id: str
    label: str
    kind: str
    box: Box
    content: str | None = None
    allowed_types: tuple[str, ...] = ()
    max_components: int = 0
    max_words: int | None = None

    @property
    def is_flexible(self) -> bool:
        return self.kind == "flexible"


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    orientation: str
    page_size: str
    width_in: float
    height_in: float
    margin_in: float
    body_pt: float
    title_pt: float
    disclaimer: str
    cut_lines: bool
    sections: tuple[TemplateSection, ...]

    def section(self, section_id: str) -> TemplateSection:
        for section in self.sections:
            if section.id == section_id:
                return section
        raise CatalogError(f"Template {self.id} has no section '{section_id}'.")

    @property
    def flexible_sections(self) -> tuple[TemplateSection, ...]:
        return tuple(section for section in self.sections if section.is_flexible)

    @property
    def has_logo_section(self) -> bool:
        return any(section.content == "logo" for section in self.sections)

    @property
    def has_footer_section(self) -> bool:
        return any(section.content == "footer" for section in self.sections)

    @property
    def safe_width_in(self) -> float:
        return self.width_in - 2 * self.margin_in

    @property
    def safe_height_in(self) -> float:
        return self.height_in - 2 * self.margin_in

    def section_size_in(self, section: TemplateSection) -> tuple[float, float]:
        return (
            round(self.safe_width_in * section.box.w / 100, 2),
            round(self.safe_height_in * section.box.h / 100, 2),
        )


@dataclass(frozen=True)
class ThemeLogo:
    id: str
    label: str
    file: str
    variant: str
    aspect: float


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    description: str
    source_url: str | None
    fonts: dict[str, dict[str, Any]]
    colors: dict[str, str]
    logos: tuple[ThemeLogo, ...]
    default_logo_id: str | None
    disclaimer: str | None
    guidance: dict[str, str]
    diagram: dict[str, Any] = field(default_factory=dict)

    def logo(self, logo_id: str) -> ThemeLogo:
        for logo in self.logos:
            if logo.id == logo_id:
                return logo
        raise CatalogError(f"Theme {self.id} has no logo '{logo_id}'.")

    @property
    def light_logos(self) -> tuple[ThemeLogo, ...]:
        return tuple(logo for logo in self.logos if logo.variant == "light")


def _parse_template(raw: dict[str, Any]) -> Template:
    page = raw["page"]
    type_scale = raw.get("type") or {}
    sections: list[TemplateSection] = []
    seen: set[str] = set()

    for item in raw["sections"]:
        section_id = str(item["id"])
        if section_id in seen:
            raise CatalogError(f"Template {raw['id']} repeats section '{section_id}'.")
        seen.add(section_id)

        box = Box(**{key: float(item["box"][key]) for key in ("x", "y", "w", "h")})
        if box.x < 0 or box.y < 0 or box.x + box.w > 100.001 or box.y + box.h > 100.001:
            raise CatalogError(f"Section {section_id} falls outside the page safe area.")

        kind = str(item["kind"])
        if kind == "flexible":
            allowed = tuple(str(value) for value in item.get("allowed_types") or ())
            if not allowed or any(value not in COMPONENT_TYPES for value in allowed):
                raise CatalogError(f"Section {section_id} has invalid allowed_types.")
            sections.append(
                TemplateSection(
                    id=section_id,
                    label=str(item["label"]),
                    kind=kind,
                    box=box,
                    allowed_types=allowed,
                    max_components=int(item.get("max_components") or 1),
                ),
            )
        elif kind == "strict":
            content = str(item.get("content") or "")
            if content not in STRICT_CONTENT:
                raise CatalogError(f"Strict section {section_id} has unknown content '{content}'.")
            max_words = item.get("max_words")
            sections.append(
                TemplateSection(
                    id=section_id,
                    label=str(item["label"]),
                    kind=kind,
                    box=box,
                    content=content,
                    max_words=int(max_words) if max_words is not None else None,
                ),
            )
        else:
            raise CatalogError(f"Section {section_id} has unknown kind '{kind}'.")

    disclaimer = str(raw.get("disclaimer") or "footer")
    if disclaimer not in DISCLAIMER_PLACEMENTS:
        raise CatalogError(f"Template {raw['id']} has unknown disclaimer placement.")
    if disclaimer == "footer" and not any(section.content == "footer" for section in sections):
        raise CatalogError(f"Template {raw['id']} places the disclaimer in a footer it lacks.")

    return Template(
        id=str(raw["id"]),
        name=str(raw["name"]),
        description=str(raw.get("description") or ""),
        orientation=str(raw.get("orientation") or "portrait"),
        page_size=str(page.get("size") or "Letter"),
        width_in=float(page["width_in"]),
        height_in=float(page["height_in"]),
        margin_in=float(page.get("margin_in") or 0),
        body_pt=float(type_scale.get("body_pt") or 10.5),
        title_pt=float(type_scale.get("title_pt") or 24),
        disclaimer=disclaimer,
        cut_lines=bool(raw.get("cut_lines")),
        sections=tuple(sections),
    )


def _parse_theme(raw: dict[str, Any]) -> Theme:
    logos = tuple(
        ThemeLogo(
            id=str(item["id"]),
            label=str(item["label"]),
            file=str(item["file"]),
            variant=str(item.get("variant") or "light"),
            aspect=float(item.get("aspect") or 1),
        )
        for item in raw.get("logos") or ()
    )
    for logo in logos:
        if not asset_path(logo.file).is_file():
            raise CatalogError(f"Theme {raw['id']} logo file is missing: {logo.file}")

    default_logo_id = raw.get("default_logo_id")
    if default_logo_id and default_logo_id not in {logo.id for logo in logos}:
        raise CatalogError(f"Theme {raw['id']} default logo is not in its logo list.")

    return Theme(
        id=str(raw["id"]),
        name=str(raw["name"]),
        description=str(raw.get("description") or ""),
        source_url=raw.get("source_url"),
        fonts=dict(raw["fonts"]),
        colors={str(key): str(value) for key, value in raw["colors"].items()},
        logos=logos,
        default_logo_id=str(default_logo_id) if default_logo_id else None,
        disclaimer=(str(raw["disclaimer"]).strip() or None) if raw.get("disclaimer") else None,
        guidance={str(key): str(value) for key, value in (raw.get("guidance") or {}).items()},
        diagram=dict(raw.get("diagram") or {}),
    )


def _load_json_dir(folder: str) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((CATALOG_DIR / folder).glob("*.json"))
    ]


@lru_cache
def load_templates() -> dict[str, Template]:
    return {template.id: template for template in map(_parse_template, _load_json_dir("templates"))}


@lru_cache
def load_themes() -> dict[str, Theme]:
    return {theme.id: theme for theme in map(_parse_theme, _load_json_dir("themes"))}


def get_template(template_id: str) -> Template:
    template = load_templates().get(template_id)
    if template is None:
        raise CatalogError(f"Unknown template '{template_id}'.")
    return template


def get_theme(theme_id: str) -> Theme:
    theme = load_themes().get(theme_id)
    if theme is None:
        raise CatalogError(f"Unknown theme '{theme_id}'.")
    return theme


def asset_path(relative: str) -> Path:
    candidate = (ASSETS_DIR / relative).resolve()
    if ASSETS_DIR.resolve() not in candidate.parents:
        raise CatalogError("Asset path escapes the catalog.")
    return candidate


def asset_data_uri(relative: str) -> str:
    path = asset_path(relative)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def resolve_options(theme: Theme, template: Template, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the user's per-material options against the theme and template.

    ``logo_locked`` turns the template's logo section into a locked theme logo.
    Without it the logo section stays empty.
    """
    raw = raw or {}
    can_lock_logo = template.has_logo_section and bool(theme.light_logos)
    logo_locked = bool(raw.get("logo_locked")) and can_lock_logo

    logo_id: str | None = None
    if logo_locked:
        requested = str(raw.get("logo_id") or theme.default_logo_id or theme.light_logos[0].id)
        logo = theme.logo(requested)
        if logo.variant != "light":
            raise CatalogError("Pick a logo drawn for light backgrounds.")
        logo_id = logo.id

    footer_text = " ".join(str(raw.get("footer_text") or "").split())
    if footer_text:
        if not template.has_footer_section:
            raise CatalogError(f"{template.name} has no footer for footer text.")
        footer = next(section for section in template.sections if section.content == "footer")
        if footer.max_words is not None and len(footer_text.split()) > footer.max_words:
            raise CatalogError(f"Footer text is limited to {footer.max_words} words.")

    return {"logo_locked": logo_locked, "logo_id": logo_id, "footer_text": footer_text}


def theme_public_payload(theme: Theme) -> dict[str, Any]:
    return {
        "id": theme.id,
        "name": theme.name,
        "description": theme.description,
        "source_url": theme.source_url,
        "colors": theme.colors,
        "fonts": theme.fonts,
        "disclaimer": theme.disclaimer,
        "default_logo_id": theme.default_logo_id,
        "logos": [
            {
                "id": logo.id,
                "label": logo.label,
                "variant": logo.variant,
                "aspect": logo.aspect,
                "asset": logo.file,
            }
            for logo in theme.logos
        ],
    }


def template_public_payload(template: Template) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "orientation": template.orientation,
        "page": {
            "size": template.page_size,
            "width_in": template.width_in,
            "height_in": template.height_in,
            "margin_in": template.margin_in,
        },
        "disclaimer": template.disclaimer,
        "cut_lines": template.cut_lines,
        "has_logo_section": template.has_logo_section,
        "sections": [
            {
                "id": section.id,
                "label": section.label,
                "kind": section.kind,
                "content": section.content,
                "allowed_types": list(section.allowed_types),
                "max_components": section.max_components,
                "max_words": section.max_words,
                "box": {"x": section.box.x, "y": section.box.y, "w": section.box.w, "h": section.box.h},
                "size_in": list(template.section_size_in(section)),
            }
            for section in template.sections
        ],
    }
