"""Build renderer input from stored rows (shared by the API preview and the worker)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.mathesys.study_material.catalog import get_template, get_theme
from app.mathesys.study_material.layout import (
    SectionLayout,
    layout_from_stored,
    normalize_section_layout,
)
from app.mathesys.study_material.render import RenderComponent, RenderInput

VISUAL_TYPES = frozenset({"diagram", "image"})


def active_version(component: dict[str, Any], versions_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    version_id = component.get("active_version_id")
    return versions_by_id.get(str(version_id)) if version_id else None


def build_render_input(
    material: dict[str, Any],
    components: list[dict[str, Any]],
    versions_by_id: dict[str, dict[str, Any]],
    *,
    image_src: Callable[[str], str],
    layout_override: dict[str, SectionLayout] | None = None,
) -> RenderInput:
    template = get_template(str(material["template_id"]))
    theme = get_theme(str(material["theme_id"]))

    render_components: list[RenderComponent] = []
    for component in sorted(components, key=lambda row: (row.get("position") or 0, str(row["id"]))):
        version = active_version(component, versions_by_id)
        if version is None:
            continue
        output = version.get("output") or {}
        component_type = str(component["component_type"])
        if component_type == "text":
            render_components.append(
                RenderComponent(
                    id=str(component["id"]),
                    section_id=str(component["section_id"]),
                    component_type="text",
                    html=str(output.get("html") or ""),
                ),
            )
        elif component_type == "diagram":
            render_components.append(
                RenderComponent(
                    id=str(component["id"]),
                    section_id=str(component["section_id"]),
                    component_type="diagram",
                    svg=str(output.get("svg") or ""),
                    caption=str(output.get("caption") or ""),
                    alt=str(output.get("alt") or ""),
                ),
            )
        elif component_type == "image" and version.get("output_path"):
            render_components.append(
                RenderComponent(
                    id=str(component["id"]),
                    section_id=str(component["section_id"]),
                    component_type="image",
                    image_src=image_src(str(version["output_path"])),
                    alt=str(output.get("alt") or ""),
                ),
            )

    if layout_override is not None:
        layout = layout_override
    else:
        stored = layout_from_stored(material.get("layout"))
        layout = {}
        for section in template.flexible_sections:
            ids = [item.id for item in render_components if item.section_id == section.id]
            if not ids:
                continue
            width_in, height_in = template.section_size_in(section)
            layout[section.id] = normalize_section_layout(
                stored.get(section.id),
                ids,
                {item.id for item in render_components if item.section_id == section.id and item.is_visual},
                section_aspect=width_in / height_in if height_in else 1.0,
            )

    return RenderInput(
        title=str(material["title"]),
        template=template,
        theme=theme,
        options=dict(material.get("options") or {}),
        components=render_components,
        layout=layout,
    )
