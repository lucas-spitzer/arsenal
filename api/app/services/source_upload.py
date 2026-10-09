from __future__ import annotations

import os
import re

from app.intellex.ingest import PDF_MIME_TYPES
from app.knowledge.structured_notes import StructuredNotesError, require_structured_notes

PDF_MAGIC = b"%PDF-"
MAX_FILENAME_LENGTH = 255
_INVALID_FILENAME_CHARS = re.compile(r"[^\w.\- ()]")


class SourceUploadValidationError(ValueError):
    """Raised when an uploaded source file fails validation."""


def sanitize_upload_filename(filename: str) -> str:
    """Return a basename-only filename safe for storage paths."""
    basename = os.path.basename(filename.strip())

    if not basename or basename in {".", ".."}:
        raise SourceUploadValidationError("Uploaded file must include a valid filename.")

    if "/" in basename or "\\" in basename or ".." in basename:
        raise SourceUploadValidationError("Filename must not contain path separators.")

    if len(basename) > MAX_FILENAME_LENGTH:
        raise SourceUploadValidationError(
            f"Filename must be {MAX_FILENAME_LENGTH} characters or fewer.",
        )

    if _INVALID_FILENAME_CHARS.search(basename):
        raise SourceUploadValidationError(
            "Filename contains unsupported characters.",
        )

    return basename


def resolve_source_mime_type(
    *,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> str:
    """Resolve MIME type for an uploaded PDF or markdown source."""
    declared_type = (content_type or "").split(";", 1)[0].strip().lower()
    filename_lower = filename.lower()

    if filename_lower.endswith(".pdf") or declared_type in PDF_MIME_TYPES:
        if not content.startswith(PDF_MAGIC):
            raise SourceUploadValidationError("Uploaded file is not a valid PDF.")
        return declared_type if declared_type in PDF_MIME_TYPES else "application/pdf"

    if filename_lower.endswith((".md", ".markdown")):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceUploadValidationError("Markdown must be valid UTF-8.") from exc
        return "text/markdown"

    raise SourceUploadValidationError("Only PDF and markdown sources are supported.")


def validate_source_upload(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    max_bytes: int,
) -> tuple[str, str]:
    """Validate upload input and return (safe_filename, mime_type)."""
    if not filename:
        raise SourceUploadValidationError("Uploaded file must include a filename.")

    if not content:
        raise SourceUploadValidationError("Uploaded file is empty.")

    if len(content) > max_bytes:
        max_megabytes = max_bytes // (1024 * 1024)
        raise SourceUploadValidationError(
            f"Uploaded file exceeds the {max_megabytes} MB limit.",
        )

    safe_filename = sanitize_upload_filename(filename)
    mime_type = resolve_source_mime_type(
        filename=safe_filename,
        content_type=content_type,
        content=content,
    )

    return safe_filename, mime_type


STRUCTURED_DATA_MIME_TYPE = "application/json"


def validate_structured_data_upload(
    *,
    filename: str | None,
    content: bytes,
    max_bytes: int,
) -> tuple[str, str]:
    """Validate a structured data (JSON) upload and return (safe_filename, mime_type).

    Structured data is stored as-is. It must be a ``.json`` file holding terms
    and lists the knowledge forge can read.
    """
    if not filename:
        raise SourceUploadValidationError("Uploaded file must include a filename.")

    if not content:
        raise SourceUploadValidationError("Uploaded file is empty.")

    if len(content) > max_bytes:
        max_megabytes = max_bytes // (1024 * 1024)
        raise SourceUploadValidationError(
            f"Uploaded file exceeds the {max_megabytes} MB limit.",
        )

    safe_filename = sanitize_upload_filename(filename)
    if not safe_filename.lower().endswith(".json"):
        raise SourceUploadValidationError("Structured data must be a .json file.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceUploadValidationError("Structured data must be valid UTF-8.") from exc

    try:
        require_structured_notes(text, filename=safe_filename)
    except StructuredNotesError as exc:
        raise SourceUploadValidationError(str(exc)) from exc

    return safe_filename, STRUCTURED_DATA_MIME_TYPE
