"""Validation and storage keys for Academy ELO lesson files.

Lesson files live in their own bucket and never become `sources` rows.
"""

from __future__ import annotations

import os
import uuid

from app.services.source_upload import SourceUploadValidationError, sanitize_upload_filename

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

# extension -> (mime type, required leading bytes or None for UTF-8 text)
LESSON_FILE_TYPES: dict[str, tuple[str, bytes | None]] = {
    ".pdf": ("application/pdf", PDF_MAGIC),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ZIP_MAGIC,
    ),
    ".ppt": ("application/vnd.ms-powerpoint", OLE_MAGIC),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ZIP_MAGIC,
    ),
    ".doc": ("application/msword", OLE_MAGIC),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ZIP_MAGIC),
    ".xls": ("application/vnd.ms-excel", OLE_MAGIC),
    ".txt": ("text/plain", None),
    ".png": ("image/png", PNG_MAGIC),
    ".jpg": ("image/jpeg", JPEG_MAGIC),
    ".jpeg": ("image/jpeg", JPEG_MAGIC),
}

SEARCHABLE_EXTENSIONS = frozenset({".pdf", ".pptx", ".docx", ".txt"})

ALLOWED_EXTENSIONS_LABEL = "PDF, PPT/PPTX, DOC/DOCX, XLS/XLSX, TXT, PNG, or JPG"


class LessonFileValidationError(ValueError):
    """Raised when an uploaded lesson file fails validation."""


def file_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def validate_lesson_file(
    *,
    filename: str | None,
    content: bytes,
    max_bytes: int,
) -> tuple[str, str]:
    """Return a safe filename and MIME type, or raise LessonFileValidationError."""
    try:
        safe_name = sanitize_upload_filename(filename or "")
    except SourceUploadValidationError as exc:
        raise LessonFileValidationError(str(exc)) from exc

    if not content:
        raise LessonFileValidationError(f"{safe_name} is empty.")
    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise LessonFileValidationError(f"{safe_name} is larger than {limit_mb} MB.")

    spec = LESSON_FILE_TYPES.get(file_extension(safe_name))
    if spec is None:
        raise LessonFileValidationError(
            f"{safe_name}: only {ALLOWED_EXTENSIONS_LABEL} files can be uploaded."
        )
    mime_type, magic = spec
    if magic is None:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LessonFileValidationError(f"{safe_name} must be UTF-8 text.") from exc
    elif not content.startswith(magic):
        raise LessonFileValidationError(f"{safe_name} does not match its file type.")
    return safe_name, mime_type


def skip_reason(filename: str) -> str | None:
    """Why a stored file cannot be searched by Discussions, or None if it can."""
    extension = file_extension(filename)
    if extension in SEARCHABLE_EXTENSIONS:
        return None
    if extension in {".ppt", ".doc"}:
        return "Older Office format. Save as PPTX, DOCX, or PDF to make it searchable."
    if extension in {".xls", ".xlsx"}:
        return "Spreadsheets are not searchable. Save as PDF to make it searchable."
    return "Images are not searchable (no text to read)."


def lesson_storage_path(workspace_slug: str, lesson_id: str, filename: str) -> str:
    key = filename.replace(" ", "-")
    return f"{workspace_slug}/{lesson_id}/{uuid.uuid4().hex[:12]}-{key}"
