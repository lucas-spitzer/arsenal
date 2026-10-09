"""Transcribe wiki note attachments into markdown for structuring.

Text formats (``.md``, ``.txt``) are decoded as UTF-8. JSON is not a note
attachment; upload it as a structured data source instead. Binary formats (PDF, DOCX, images) go through LlamaParse. Multi-file batches
are concatenated in upload order with ``\\n\\n---\\n\\n`` separators.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from app.artifact_paths import drafts_path
from app.services.llamaparse_client import LlamaParseClient, LlamaParseError

_INVALID_FILENAME_CHARS = re.compile(r"[^\w.\- ()]")
MAX_FILENAME_LENGTH = 255

# Passthrough — no LlamaParse.
TEXT_EXTENSIONS = {".md", ".txt", ".markdown"}
TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/markdown",
}
JSON_MIME_TYPES = {"application/json", "text/json"}

# Binary — LlamaParse.
BINARY_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".heic",
    ".heif",
    ".webp",
    ".tif",
    ".tiff",
    ".gif",
    ".bmp",
}

EXTENSION_MIME: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

ALLOWED_MIME_TYPES = set(EXTENSION_MIME.values()) | {
    "application/x-pdf",
    "image/jpg",
}

FILE_SEPARATOR = "\n\n---\n\n"


class WikiTranscriptionError(ValueError):
    """Invalid note attachment or transcription failure."""


@dataclass(frozen=True)
class ValidatedAttachment:
    order: int
    filename: str
    mime_type: str
    content: bytes
    is_text: bool


def sanitize_attachment_filename(filename: str) -> str:
    basename = os.path.basename(filename.strip())

    if not basename or basename in {".", ".."}:
        raise WikiTranscriptionError("Uploaded file must include a valid filename.")

    # basename() already strips directories; keep an explicit guard for clarity.
    if "/" in basename or "\\" in basename:
        raise WikiTranscriptionError("Filename must not contain path separators.")

    if len(basename) > MAX_FILENAME_LENGTH:
        raise WikiTranscriptionError(
            f"Filename must be {MAX_FILENAME_LENGTH} characters or fewer.",
        )

    if _INVALID_FILENAME_CHARS.search(basename):
        raise WikiTranscriptionError("Filename contains unsupported characters.")

    return basename


def _extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def resolve_attachment_mime_type(
    *,
    filename: str,
    content_type: str | None,
) -> tuple[str, bool]:
    """Return ``(mime_type, is_text)`` for an allowed note attachment."""
    ext = _extension(filename)
    declared = (content_type or "").split(";", 1)[0].strip().lower()

    if ext == ".json" or (
        declared in JSON_MIME_TYPES and ext not in TEXT_EXTENSIONS and ext not in BINARY_EXTENSIONS
    ):
        raise WikiTranscriptionError(
            "JSON is not a notes file. Upload it as a structured data source "
            "in Sources, then pick it when you start the project.",
        )

    if ext in TEXT_EXTENSIONS or declared in TEXT_MIME_TYPES:
        mime = (
            declared
            if declared in TEXT_MIME_TYPES
            else EXTENSION_MIME.get(ext, "text/plain")
        )
        return mime, True

    if ext in BINARY_EXTENSIONS:
        mime = (
            declared
            if declared in ALLOWED_MIME_TYPES
            else EXTENSION_MIME.get(ext, "application/octet-stream")
        )
        return mime, False

    if declared in TEXT_MIME_TYPES:
        return declared, True

    if declared in ALLOWED_MIME_TYPES:
        return declared, False

    raise WikiTranscriptionError(
        "Unsupported file type. Allowed: .md, .txt, .pdf, .docx, "
        "and images (.png, .jpg, .jpeg, .heic, .webp, .tiff, …).",
    )


def validate_note_attachment(
    *,
    order: int,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    max_bytes: int,
) -> ValidatedAttachment:
    if not filename:
        raise WikiTranscriptionError("Uploaded file must include a filename.")

    if not content:
        raise WikiTranscriptionError(f"Uploaded file '{filename}' is empty.")

    if len(content) > max_bytes:
        max_megabytes = max_bytes // (1024 * 1024)
        raise WikiTranscriptionError(
            f"Uploaded file '{filename}' exceeds the {max_megabytes} MB limit.",
        )

    safe_name = sanitize_attachment_filename(filename)
    mime_type, is_text = resolve_attachment_mime_type(
        filename=safe_name,
        content_type=content_type,
    )
    return ValidatedAttachment(
        order=order,
        filename=safe_name,
        mime_type=mime_type,
        content=content,
        is_text=is_text,
    )


def attachment_storage_path(
    *,
    workspace_slug: str,
    batch_slug: str,
    order: int,
    filename: str,
) -> str:
    return drafts_path(workspace_slug, batch_slug, f"{order:02d}_{filename}")


def decode_text_attachment(content: bytes, *, filename: str) -> str:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise WikiTranscriptionError(
            f"Could not decode '{filename}' as UTF-8 text.",
        ) from exc

    stripped = text.strip()
    if not stripped:
        raise WikiTranscriptionError(f"Text file '{filename}' is empty.")
    return stripped


def concatenate_transcriptions(parts: list[str]) -> str:
    cleaned = [part.strip() for part in parts if part.strip()]
    return FILE_SEPARATOR.join(cleaned)


def transcribe_attachment_content(
    attachment: ValidatedAttachment | dict[str, Any],
    content: bytes,
    *,
    llamaparse: LlamaParseClient | None = None,
) -> str:
    """Transcribe one attachment's bytes to markdown/plain text."""
    if isinstance(attachment, ValidatedAttachment):
        filename = attachment.filename
        mime_type = attachment.mime_type
        is_text = attachment.is_text
    else:
        filename = str(attachment.get("filename") or "notes")
        mime_type = str(attachment.get("mime_type") or "application/octet-stream")
        is_text = _extension(filename) in TEXT_EXTENSIONS or mime_type in TEXT_MIME_TYPES

    if is_text:
        return decode_text_attachment(content, filename=filename)

    client = llamaparse or LlamaParseClient()
    try:
        result = client.parse_file(
            filename=filename,
            content=content,
            content_type=mime_type,
        )
    except LlamaParseError as exc:
        raise WikiTranscriptionError(
            f"Failed to transcribe '{filename}': {exc}",
        ) from exc

    markdown = (result.raw_markdown or "").strip()
    if not markdown:
        raise WikiTranscriptionError(
            f"Transcription of '{filename}' produced no text.",
        )
    return markdown


def transcribe_attachments_in_order(
    items: list[tuple[dict[str, Any], bytes]],
    *,
    llamaparse: LlamaParseClient | None = None,
) -> str:
    """Transcribe ``(attachment_meta, content)`` pairs and concatenate."""
    if not items:
        raise WikiTranscriptionError("No attachments to transcribe.")

    parts: list[str] = []
    for meta, content in sorted(
        items,
        key=lambda pair: int(pair[0].get("order") or 0),
    ):
        parts.append(
            transcribe_attachment_content(meta, content, llamaparse=llamaparse),
        )

    combined = concatenate_transcriptions(parts)
    if not combined.strip():
        raise WikiTranscriptionError("Transcription produced no text.")
    return combined
