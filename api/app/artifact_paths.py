"""Library object keys in the sources bucket.

Layout (no UUIDs in keys):

    {workspace_slug}/{source_slug}/{original filename}
    {workspace_slug}/{source_slug}/book.epub
    {workspace_slug}/{source_slug}/narration.json
    {workspace_slug}/{source_slug}/wiki.json
    {workspace_slug}/{source_slug}/audio/{provider}/{model_id}/{voice_id}/{clip}
    {workspace_slug}/{source_slug}/work/{parse.md|pages.json|normalized.json|trimmed.json|book.json}
    {workspace_slug}/drafts/{batch_slug}/{file}
    {workspace_slug}/study-material/{material_slug}/files/{component_id}/{file}
    {workspace_slug}/study-material/{material_slug}/components/{component_id}/v{n}.{png|svg|html}
    {workspace_slug}/study-material/{material_slug}/{draft.html|material.html|material.pdf}
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

OUTPUT_FILENAMES = {
    "electronic_book": "book.epub",
    "narration_audio": "narration.json",
    "wiki_json": "wiki.json",
}

STUDY_MATERIAL_DRAFT = "draft.html"
STUDY_MATERIAL_FINAL_HTML = "material.html"
STUDY_MATERIAL_FINAL_PDF = "material.pdf"

WORK_PARSE = "parse.md"
WORK_PAGES = "pages.json"
WORK_NORMALIZED = "normalized.json"
WORK_TRIMMED = "trimmed.json"
WORK_BOOK = "book.json"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def storage_slug(label: str, *, fallback: str = "untitled") -> str:
    normalized = unicodedata.normalize("NFKD", label)
    ascii_label = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_label.lower()).strip("-")
    return slug or fallback


def slug_from_filename(filename: str) -> str:
    basename = os.path.basename(filename.strip())
    stem, _dot, _ext = basename.partition(".")
    return storage_slug(stem or basename, fallback="source")


def next_available_slug(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    index = 2
    candidate = f"{base}-{index}"
    while candidate in taken:
        index += 1
        candidate = f"{base}-{index}"
    return candidate


def source_folder(workspace_slug: str, source_slug: str) -> str:
    return f"{workspace_slug}/{source_slug}"


def original_path(workspace_slug: str, source_slug: str, filename: str) -> str:
    return f"{source_folder(workspace_slug, source_slug)}/{filename}"


def work_path(workspace_slug: str, source_slug: str, filename: str) -> str:
    return f"{source_folder(workspace_slug, source_slug)}/work/{filename}"


def output_path(workspace_slug: str, source_slug: str, artifact_type: str) -> str:
    try:
        filename = OUTPUT_FILENAMES[artifact_type]
    except KeyError as exc:
        raise ValueError(f"Unknown artifact type: {artifact_type}") from exc
    return f"{source_folder(workspace_slug, source_slug)}/{filename}"


def audio_clip_path(
    workspace_slug: str,
    source_slug: str,
    provider: str,
    model_id: str,
    voice_id: str,
    filename: str,
) -> str:
    variant_path = "/".join(
        (
            storage_slug(provider, fallback="tts"),
            storage_slug(model_id, fallback="model"),
            storage_slug(voice_id, fallback="voice"),
        )
    )
    return f"{source_folder(workspace_slug, source_slug)}/audio/{variant_path}/{filename}"


def drafts_path(workspace_slug: str, batch_slug: str, filename: str) -> str:
    return f"{workspace_slug}/drafts/{batch_slug}/{filename}"


def study_material_folder(workspace_slug: str, material_slug: str) -> str:
    return f"{workspace_slug}/study-material/{material_slug}"


def study_material_file_path(
    workspace_slug: str,
    material_slug: str,
    component_id: str,
    filename: str,
) -> str:
    folder = study_material_folder(workspace_slug, material_slug)
    return f"{folder}/files/{component_id}/{filename}"


def study_material_component_output_path(
    workspace_slug: str,
    material_slug: str,
    component_id: str,
    version: int,
    extension: str,
) -> str:
    folder = study_material_folder(workspace_slug, material_slug)
    return f"{folder}/components/{component_id}/v{version}.{extension.lstrip('.')}"


def study_material_output_path(workspace_slug: str, material_slug: str, filename: str) -> str:
    return f"{study_material_folder(workspace_slug, material_slug)}/{filename}"


def location_from_source(source: dict[str, Any]) -> tuple[str, str]:
    workspace_slug = str(source.get("workspace_slug") or "").strip()
    source_slug = str(source.get("slug") or "").strip()
    if not workspace_slug or not source_slug:
        raise ValueError("Source is missing workspace_slug or slug.")
    return workspace_slug, source_slug


def parse_work_path(source: dict[str, Any]) -> str:
    workspace_slug, source_slug = location_from_source(source)
    return work_path(workspace_slug, source_slug, WORK_PARSE)


def pages_work_path(source: dict[str, Any]) -> str:
    workspace_slug, source_slug = location_from_source(source)
    return work_path(workspace_slug, source_slug, WORK_PAGES)


def normalized_work_path(source: dict[str, Any]) -> str:
    workspace_slug, source_slug = location_from_source(source)
    return work_path(workspace_slug, source_slug, WORK_NORMALIZED)


def trimmed_work_path(source: dict[str, Any]) -> str:
    workspace_slug, source_slug = location_from_source(source)
    return work_path(workspace_slug, source_slug, WORK_TRIMMED)


def book_work_path(source: dict[str, Any]) -> str:
    workspace_slug, source_slug = location_from_source(source)
    return work_path(workspace_slug, source_slug, WORK_BOOK)


def downloadable_artifact_path(source: dict[str, Any], artifact_type: str) -> str:
    workspace_slug, source_slug = location_from_source(source)
    return output_path(workspace_slug, source_slug, artifact_type)


def narration_clip_path(
    source: dict[str, Any],
    provider: str,
    model_id: str,
    voice_id: str,
    chapter_id: str,
    clip_index: int,
    *,
    extension: str = "mp3",
) -> str:
    workspace_slug, source_slug = location_from_source(source)
    suffix = extension.lstrip(".") or "mp3"
    filename = f"{chapter_id}-{clip_index:02d}.{suffix}"
    return audio_clip_path(
        workspace_slug,
        source_slug,
        provider,
        model_id,
        voice_id,
        filename,
    )
