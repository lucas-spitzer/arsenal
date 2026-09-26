"""Component input files: validation on upload, text extraction at generation."""

from __future__ import annotations

from dataclasses import dataclass

import fitz

DOCUMENT_MIME_TYPES = frozenset({"application/pdf", "text/markdown", "text/plain", "text/csv"})
IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
ALLOWED_MIME_TYPES = DOCUMENT_MIME_TYPES | IMAGE_MIME_TYPES
MAX_REFERENCE_CHARS = 40_000

_EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_MAGIC = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}


class ComponentFileError(ValueError):
    """An uploaded component file is the wrong type, too large, or unreadable."""


@dataclass(frozen=True)
class ComponentFile:
    filename: str
    mime_type: str
    content: bytes

    @property
    def is_image(self) -> bool:
        return self.mime_type in IMAGE_MIME_TYPES


def resolve_component_file_mime(*, filename: str, content_type: str | None, content: bytes) -> str:
    lowered = filename.lower()
    extension = lowered[lowered.rfind(".") :] if "." in lowered else ""
    mime = _EXTENSION_MIME.get(extension) or (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:
        raise ComponentFileError("Attach PDF, markdown, text, CSV, PNG, JPEG, or WebP files.")
    magic = _MAGIC.get(mime)
    if magic and not any(content.startswith(prefix) for prefix in magic):
        raise ComponentFileError(f"{filename} does not look like a valid {mime} file.")
    if mime in {"text/markdown", "text/plain", "text/csv"}:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ComponentFileError(f"{filename} must be UTF-8 text.") from exc
    return mime


def _pdf_text(content: bytes) -> str:
    document = fitz.open(stream=content, filetype="pdf")
    try:
        return "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()


def reference_text(files: list[ComponentFile], *, limit: int = MAX_REFERENCE_CHARS) -> str:
    """Concatenate document text for the prompt; images are passed separately."""
    blocks: list[str] = []
    remaining = limit
    for item in files:
        if item.is_image or remaining <= 0:
            continue
        if item.mime_type == "application/pdf":
            body = _pdf_text(item.content)
        else:
            body = item.content.decode("utf-8", errors="replace")
        body = body.strip()[:remaining]
        if not body:
            continue
        blocks.append(f"--- {item.filename} ---\n{body}")
        remaining -= len(body)
    return "\n\n".join(blocks)
