"""Rules for configuring Study Material: status gates, placement, settings."""

from __future__ import annotations

from typing import Any

from app.mathesys.study_material.catalog import (
    CatalogError,
    Template,
    Theme,
    resolve_options,
)
from app.mathesys.study_material.images import resolve_image_settings

EDITABLE_STATUSES = frozenset({"configuring", "draft", "failed"})
GENERATABLE_STATUSES = EDITABLE_STATUSES
BUSY_STATUSES = frozenset({"generating", "finalizing"})
MAX_SECTION_NOTE_CHARS = 500


class StudyMaterialRuleError(ValueError):
    """The request breaks a template, theme, or status rule."""


def ensure_editable(material: dict[str, Any]) -> None:
    status = str(material.get("status"))
    if status == "finalized":
        raise StudyMaterialRuleError("This study material is finalized. Return it to editing first.")
    if status not in EDITABLE_STATUSES:
        raise StudyMaterialRuleError("Wait for the current run to finish before editing.")


def material_options(theme: Theme, template: Template, raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    try:
        options = resolve_options(theme, template, raw)
    except CatalogError as exc:
        raise StudyMaterialRuleError(str(exc)) from exc

    flexible_ids = {section.id for section in template.flexible_sections}
    notes: dict[str, str] = {}
    for section_id, note in (raw.get("section_notes") or {}).items():
        text = " ".join(str(note or "").split())[:MAX_SECTION_NOTE_CHARS]
        if section_id in flexible_ids and text:
            notes[section_id] = text
    options["section_notes"] = notes
    return options


def validate_placement(
    template: Template,
    *,
    section_id: str,
    component_type: str,
    section_component_count: int,
) -> None:
    try:
        section = template.section(section_id)
    except CatalogError as exc:
        raise StudyMaterialRuleError(str(exc)) from exc
    if not section.is_flexible:
        raise StudyMaterialRuleError(f"{section.label} is locked to its template content.")
    if component_type not in section.allowed_types:
        raise StudyMaterialRuleError(f"{section.label} does not accept {component_type} components.")
    if section_component_count >= section.max_components:
        raise StudyMaterialRuleError(
            f"{section.label} holds at most {section.max_components} components.",
        )


def component_settings(component_type: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    if component_type == "image":
        return resolve_image_settings(raw)
    return {}


def ensure_generatable(material: dict[str, Any], components: list[dict[str, Any]]) -> None:
    if str(material.get("status")) not in GENERATABLE_STATUSES:
        raise StudyMaterialRuleError("This study material cannot be generated in its current state.")
    if not components:
        raise StudyMaterialRuleError("Add at least one component before generating.")


def serialize_material(
    material: dict[str, Any],
    components: list[dict[str, Any]] | None = None,
    versions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    versions = versions or []
    by_id = {str(row["id"]): row for row in versions}
    counts: dict[str, int] = {}
    for row in versions:
        counts[str(row["component_id"])] = counts.get(str(row["component_id"]), 0) + 1

    serialized_components = []
    for component in components or []:
        active_id = component.get("active_version_id")
        serialized_components.append(
            {
                **component,
                "files": [
                    {
                        "id": str(item.get("id")),
                        "filename": str(item.get("filename")),
                        "mime_type": str(item.get("mime_type")),
                        "file_size_bytes": int(item.get("file_size_bytes") or 0),
                    }
                    for item in component.get("files") or []
                ],
                "active_version": by_id.get(str(active_id)) if active_id else None,
                "version_count": counts.get(str(component["id"]), 0),
            },
        )
    return {
        **material,
        "component_count": len(serialized_components),
        "components": serialized_components,
    }
