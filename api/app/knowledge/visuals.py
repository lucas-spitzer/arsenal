"""Optional uploaded images on flashcards, questions, and scenarios."""

from __future__ import annotations

from typing import Any

from app.mathesys.study_material.inputs import IMAGE_MIME_TYPES, resolve_component_file_mime
from app.services.source_upload import sanitize_upload_filename

ITEM_TYPES = ("flashcard", "question", "scenario")
VISUAL_KINDS = ("icon", "diagram", "example")
PLACEMENTS: dict[str, tuple[str, ...]] = {
    "flashcard": ("front", "back", "beside", "front_with_label"),
    "question": ("stem",),
    "scenario": ("situation",),
}
DEFAULT_PLACEMENT = {
    "flashcard": "back",
    "question": "stem",
    "scenario": "situation",
}


class VisualError(ValueError):
    """An uploaded image or its placement is not usable."""


def default_placement(item_type: str) -> str:
    try:
        return DEFAULT_PLACEMENT[item_type]
    except KeyError as exc:
        raise VisualError(f"Unknown item type {item_type}.") from exc


def normalize_visual(
    *,
    item_type: str,
    kind: str,
    placement: str | None,
    alt: str | None,
    storage_path: str,
    mime_type: str,
    filename: str,
    byte_size: int,
) -> dict[str, Any]:
    if item_type not in PLACEMENTS:
        raise VisualError(f"Unknown item type {item_type}.")
    cleaned_kind = kind.strip().lower()
    if cleaned_kind not in VISUAL_KINDS:
        raise VisualError("Image kind must be icon, diagram, or example.")
    cleaned_placement = (placement or default_placement(item_type)).strip().lower()
    if cleaned_placement not in PLACEMENTS[item_type]:
        allowed = ", ".join(PLACEMENTS[item_type])
        raise VisualError(f"A {item_type} image uses placement {allowed}.")
    return {
        "kind": cleaned_kind,
        "placement": cleaned_placement,
        "alt": (alt or "").strip(),
        "storage_path": storage_path,
        "mime_type": mime_type,
        "filename": filename,
        "byte_size": byte_size,
    }


def validate_image_upload(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    max_bytes: int,
) -> tuple[str, str]:
    if not content:
        raise VisualError("Uploaded file is empty.")
    if len(content) > max_bytes:
        raise VisualError(f"Images are limited to {max_bytes // (1024 * 1024)} MB.")
    try:
        safe_name = sanitize_upload_filename(filename or "")
        mime_type = resolve_component_file_mime(
            filename=safe_name,
            content_type=content_type,
            content=content,
        )
    except ValueError as exc:
        raise VisualError(str(exc)) from exc
    if mime_type not in IMAGE_MIME_TYPES:
        raise VisualError("Upload a PNG, JPEG, or WebP image.")
    return safe_name, mime_type


def cited_wiki_id(citations: list[dict[str, Any]] | None) -> str | None:
    for citation in citations or []:
        uri = str(citation.get("uri") or "")
        if uri.startswith("wiki://"):
            wiki_id = uri.removeprefix("wiki://").strip()
            if wiki_id:
                return wiki_id
    return None


def storage_path_of(visual: dict[str, Any] | None) -> str | None:
    if not isinstance(visual, dict):
        return None
    path = str(visual.get("storage_path") or "").strip()
    return path or None


def visual_for_response(visual: dict[str, Any] | None, url: str | None) -> dict[str, Any] | None:
    if not isinstance(visual, dict) or not storage_path_of(visual):
        return None
    alt = str(visual.get("alt") or "").strip()
    return {
        "kind": visual.get("kind") or "diagram",
        "placement": visual.get("placement") or "back",
        "alt": alt or None,
        "mime_type": visual.get("mime_type"),
        "filename": visual.get("filename"),
        "url": url,
    }
