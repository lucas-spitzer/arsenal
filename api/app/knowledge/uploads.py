"""Turn a Design Forge upload into notes bytes plus named question images.

One file is notes, as before. A zip, or a JSON file selected with images,
also carries the pictures a question pack names.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.knowledge.visuals import VisualError, validate_image_upload

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_QUESTION_IMAGES = 25


class KnowledgeUploadError(ValueError):
    """The notes file and its images cannot be read together."""


@dataclass(frozen=True)
class UploadedPart:
    filename: str
    content_type: str | None
    content: bytes


@dataclass(frozen=True)
class ResolvedUpload:
    filename: str | None
    content_type: str | None
    content: bytes | None
    images: dict[str, bytes]


def resolve_knowledge_upload(parts: list[UploadedPart], *, max_bytes: int) -> ResolvedUpload:
    """Return the notes file and a map of image base name to bytes."""
    if not parts:
        return ResolvedUpload(filename=None, content_type=None, content=None, images={})
    if len(parts) > 1 and any(_is_zip(part.filename) for part in parts):
        raise KnowledgeUploadError("Upload a zip by itself, or the JSON file and its images.")
    if len(parts) == 1 and _is_zip(parts[0].filename):
        return _from_zip(parts[0], max_bytes=max_bytes)
    if len(parts) == 1:
        part = parts[0]
        return ResolvedUpload(
            filename=part.filename,
            content_type=part.content_type,
            content=part.content,
            images={},
        )
    notes = [part for part in parts if part.filename.lower().endswith(".json")]
    if len(notes) != 1:
        raise KnowledgeUploadError("Select one JSON notes file and its images.")
    images = _image_map(
        ((part.filename, part.content) for part in parts if part is not notes[0]),
        max_bytes=max_bytes,
    )
    note = notes[0]
    return ResolvedUpload(
        filename=note.filename,
        content_type=note.content_type or "application/json",
        content=note.content,
        images=images,
    )


def require_question_images(
    questions: list[dict[str, Any]],
    images: dict[str, bytes],
    *,
    max_bytes: int,
) -> None:
    """Reject a pack whose named pictures are missing or not a usable image."""
    for index, question in enumerate(questions, start=1):
        image = question.get("image")
        if not isinstance(image, dict):
            continue
        filename = str(image.get("filename") or "")
        content = images.get(filename)
        if content is None:
            raise KnowledgeUploadError(f"Question {index} image '{filename}' was not in the upload.")
        try:
            validate_image_upload(
                filename=filename,
                content_type=None,
                content=content,
                max_bytes=max_bytes,
            )
        except VisualError as exc:
            raise KnowledgeUploadError(f"Question {index}: {exc}") from exc


def _from_zip(part: UploadedPart, *, max_bytes: int) -> ResolvedUpload:
    try:
        archive = zipfile.ZipFile(io.BytesIO(part.content))
    except zipfile.BadZipFile as exc:
        raise KnowledgeUploadError("Could not read the zip.") from exc
    notes: list[tuple[str, bytes]] = []
    image_members: list[tuple[str, bytes]] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir() or info.flag_bits & 0x1:
                if info.flag_bits & 0x1:
                    raise KnowledgeUploadError("The zip cannot be password protected.")
                continue
            basename = _member_basename(info.filename)
            if basename is None:
                continue
            if info.file_size > max_bytes and not basename.lower().endswith(".json"):
                raise KnowledgeUploadError(
                    f"'{basename}' is larger than {max_bytes // (1024 * 1024)} MB.",
                )
            content = archive.read(info)
            suffix = _suffix(basename)
            if suffix == ".json":
                notes.append((basename, content))
            elif suffix in _IMAGE_SUFFIXES:
                if len(content) > max_bytes:
                    raise KnowledgeUploadError(
                        f"'{basename}' is larger than {max_bytes // (1024 * 1024)} MB.",
                    )
                image_members.append((basename, content))
            else:
                raise KnowledgeUploadError("A zip can contain one JSON file and PNG, JPEG, or WebP images.")
    if len(notes) != 1:
        raise KnowledgeUploadError("A zip needs one JSON notes file.")
    filename, content = notes[0]
    return ResolvedUpload(
        filename=filename,
        content_type="application/json",
        content=content,
        images=_image_map(image_members, max_bytes=max_bytes),
    )


def _image_map(members: Iterable[tuple[str, bytes]], *, max_bytes: int) -> dict[str, bytes]:
    images: dict[str, bytes] = {}
    for name, content in members:
        basename = _member_basename(name)
        if basename is None:
            continue
        if _suffix(basename) not in _IMAGE_SUFFIXES:
            raise KnowledgeUploadError("The extra files must be PNG, JPEG, or WebP images.")
        if len(content) > max_bytes:
            raise KnowledgeUploadError(f"'{basename}' is larger than {max_bytes // (1024 * 1024)} MB.")
        if basename in images:
            raise KnowledgeUploadError(f"'{basename}' is in the upload more than once.")
        images[basename] = content
    if len(images) > MAX_QUESTION_IMAGES:
        raise KnowledgeUploadError(f"Upload at most {MAX_QUESTION_IMAGES} images (got {len(images)}).")
    return images


def _member_basename(name: str) -> str | None:
    """Base name of a zip member. Junk is skipped. A path that escapes is an error."""
    cleaned = name.replace("\\", "/").strip()
    if not cleaned or cleaned.endswith("/"):
        return None
    if cleaned.startswith("/") or (len(cleaned) >= 2 and cleaned[1] == ":"):
        raise KnowledgeUploadError(f"'{name}' is not a safe file name.")
    path = PurePosixPath(cleaned)
    if ".." in path.parts:
        raise KnowledgeUploadError(f"'{name}' is not a safe file name.")
    if "__MACOSX" in path.parts or path.name.lower() == ".ds_store":
        return None
    return path.name or None


def _suffix(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def _is_zip(filename: str) -> bool:
    return filename.lower().endswith(".zip")
