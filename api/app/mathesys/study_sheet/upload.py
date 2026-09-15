"""Decode markdown source bytes for study-sheet generation."""

from __future__ import annotations


class StudySheetUploadError(ValueError):
    """Raised when markdown source bytes cannot be decoded."""


def decode_markdown(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StudySheetUploadError("Markdown must be valid UTF-8.") from exc
