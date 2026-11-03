"""A source row that can be referenced before its file is uploaded."""

from __future__ import annotations

import re
from typing import Any

from app.artifact_paths import next_available_slug, storage_slug

PENDING_MIME_TYPE = "application/x-pending"
AWAITING_FILE_STATUS = "awaiting_file"
MAX_REFERENCE_NAME_LENGTH = 200
MAX_REFERENCE_BACKGROUND_LENGTH = 4000
MAX_REFERENCE_DETAIL_LENGTH = 200
_INVALID_FILENAME_CHARS = re.compile(r"[^\w.\- ()]")
_DOCUMENT_EXTENSIONS = frozenset({"pdf", "md", "markdown"})


class ReferenceSourceError(ValueError):
    """Raised when a file-less source cannot be created from the given fields."""


def reference_source_row(
    *,
    source_id: str,
    workspace_id: str,
    owner_id: str,
    name: str,
    background: str | None,
    document_type: str | None,
    issuing_authority: str | None,
    taken_slugs: set[str],
) -> dict[str, Any]:
    """Build a sources insert payload with no stored file."""
    display_name = _required_name(name)
    metadata: dict[str, str] = {"display_name": display_name}
    cleaned_background = _optional_text(
        background,
        limit=MAX_REFERENCE_BACKGROUND_LENGTH,
        label="Background",
    )
    cleaned_type = _optional_text(
        document_type,
        limit=MAX_REFERENCE_DETAIL_LENGTH,
        label="Document type",
    )
    cleaned_authority = _optional_text(
        issuing_authority,
        limit=MAX_REFERENCE_DETAIL_LENGTH,
        label="Issuing authority",
    )
    if cleaned_background:
        metadata["background"] = cleaned_background
    if cleaned_type:
        metadata["document_type"] = cleaned_type
    if cleaned_authority:
        metadata["issuing_authority"] = cleaned_authority

    slug = next_available_slug(storage_slug(display_name, fallback="source"), taken_slugs)
    return {
        "id": source_id,
        "workspace_id": workspace_id,
        "owner_id": owner_id,
        "filename": _reference_filename(display_name),
        "slug": slug,
        "mime_type": PENDING_MIME_TYPE,
        "storage_path": "",
        "file_hash": f"pending:{source_id}",
        "file_size_bytes": 0,
        "source_metadata": metadata,
        "status": AWAITING_FILE_STATUS,
        "source_kind": "document",
    }


def _required_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ReferenceSourceError("Name is required.")
    if len(cleaned) > MAX_REFERENCE_NAME_LENGTH:
        raise ReferenceSourceError(
            f"Name must be {MAX_REFERENCE_NAME_LENGTH} characters or fewer.",
        )
    return cleaned


def _optional_text(value: str | None, *, limit: int, label: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > limit:
        raise ReferenceSourceError(f"{label} must be {limit} characters or fewer.")
    return cleaned


def _reference_filename(name: str) -> str:
    """A stored filename that does not look like an uploaded document."""
    cleaned = _INVALID_FILENAME_CHARS.sub(" ", name)
    cleaned = " ".join(cleaned.split()).strip(" .")
    stem, dot, extension = cleaned.rpartition(".")
    if dot and extension.lower() in _DOCUMENT_EXTENSIONS:
        cleaned = stem.strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        return "source"
    return cleaned[:255]
