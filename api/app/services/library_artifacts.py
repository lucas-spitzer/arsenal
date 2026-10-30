"""Upload a finished library item onto an existing source.

An audiobook is one MP3 stored as an ``audiobook`` artifact. Knowledge JSON
is parsed with the structured-notes reader and written straight into wiki
entries and quiz rows. Neither path opens a knowledge project or a production run.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.artifact_paths import audiobook_object_path, next_available_slug, storage_slug
from app.intellex.wiki_candidates import promote_candidates
from app.knowledge.structured_notes import (
    StructuredNotes,
    StructuredNotesError,
    require_structured_notes,
)
from app.repositories.artifacts import ArtifactRepository
from app.repositories.assessments import AssessmentRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.services.knowledge_projects import (
    KnowledgeProjectError,
    _candidates,
    _imported_question_rows,
    citation_catalog,
)
from app.services.source_upload import SourceUploadValidationError, sanitize_upload_filename
from app.services.supabase_storage import SupabaseStorageClient

logger = logging.getLogger(__name__)

AUDIOBOOK = "audiobook"
KNOWLEDGE = "knowledge"
AUDIOBOOK_MIME = "audio/mpeg"
# A finished book is larger than a source PDF. One gibibyte covers a long MP3.
AUDIOBOOK_MAX_BYTES = 1024 * 1024 * 1024
TITLE_MAX_LENGTH = 200


class LibraryArtifactError(ValueError):
    """The upload cannot be stored as a library item."""


def clean_title(title: str) -> str:
    cleaned = " ".join(title.split())
    if not cleaned:
        raise LibraryArtifactError("Enter a title.")
    if len(cleaned) > TITLE_MAX_LENGTH:
        raise LibraryArtifactError(f"Title must be {TITLE_MAX_LENGTH} characters or fewer.")
    return cleaned


def looks_like_mp3(content: bytes) -> bool:
    """True when the bytes start with an ID3 tag or an MPEG frame sync."""
    if content.startswith(b"ID3"):
        return True
    window = content[:4096]
    return any(
        window[index] == 0xFF and (window[index + 1] & 0xE0) == 0xE0
        for index in range(max(len(window) - 1, 0))
    )


def audiobook_filename(title: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in " ._-'" else " "
        for character in title
    )
    cleaned = " ".join(cleaned.split()).strip(" .")
    return f"{cleaned or 'Audiobook'}.mp3"


async def upload_library_artifact(
    *,
    workspace_id: str,
    workspace_slug: str,
    source: dict[str, Any],
    artifact_type: str,
    title: str,
    filename: str | None,
    content: bytes,
    json_max_bytes: int,
    bucket: str,
    artifacts: ArtifactRepository,
    wiki_entries: WikiEntryRepository,
    assessments: AssessmentRepository,
    storage: SupabaseStorageClient,
) -> dict[str, Any]:
    """Store one audiobook or import one knowledge file for ``source``."""
    cleaned_title = clean_title(title)
    source_id = str(source.get("id") or "")
    source_slug = str(source.get("slug") or "").strip()
    if not source_id or not source_slug or not workspace_slug.strip():
        raise LibraryArtifactError("This source has no folder yet.")
    if not filename:
        raise LibraryArtifactError("Uploaded file must include a filename.")
    if not content:
        raise LibraryArtifactError("Uploaded file is empty.")

    kind = artifact_type.strip().lower()
    if kind == AUDIOBOOK:
        artifact = await _store_audiobook(
            workspace_id=workspace_id,
            workspace_slug=workspace_slug.strip(),
            source_id=source_id,
            source_slug=source_slug,
            title=cleaned_title,
            filename=filename,
            content=content,
            bucket=bucket,
            artifacts=artifacts,
            storage=storage,
        )
        return {
            "artifact_type": AUDIOBOOK,
            "source_id": source_id,
            "title": cleaned_title,
            "artifact": artifact,
            "wiki_entry_count": 0,
            "question_count": 0,
        }
    if kind == KNOWLEDGE:
        counts = await _import_knowledge(
            workspace_id=workspace_id,
            source_id=source_id,
            title=cleaned_title,
            filename=filename,
            content=content,
            max_bytes=json_max_bytes,
            wiki_entries=wiki_entries,
            assessments=assessments,
        )
        return {
            "artifact_type": KNOWLEDGE,
            "source_id": source_id,
            "title": cleaned_title,
            "artifact": None,
            "wiki_entry_count": counts["wiki_entry_count"],
            "question_count": counts["question_count"],
        }
    raise LibraryArtifactError("Choose an audiobook or a knowledge file.")


async def _store_audiobook(
    *,
    workspace_id: str,
    workspace_slug: str,
    source_id: str,
    source_slug: str,
    title: str,
    filename: str,
    content: bytes,
    bucket: str,
    artifacts: ArtifactRepository,
    storage: SupabaseStorageClient,
) -> dict[str, Any]:
    if len(content) > AUDIOBOOK_MAX_BYTES:
        raise LibraryArtifactError("Audiobook file exceeds the 1024 MB limit.")
    try:
        safe_filename = sanitize_upload_filename(filename)
    except SourceUploadValidationError as exc:
        raise LibraryArtifactError(str(exc)) from exc
    if not safe_filename.lower().endswith(".mp3"):
        raise LibraryArtifactError("An audiobook must be an .mp3 file.")
    if not looks_like_mp3(content):
        raise LibraryArtifactError("That file is not an MP3.")

    existing = await artifacts.list_for_source(
        source_id,
        workspace_id,
        artifact_type=AUDIOBOOK,
    )
    taken = {
        str(row.get("storage_path") or "").rsplit("/", 1)[-1].removesuffix(".mp3")
        for row in existing
    }
    stored_name = f"{next_available_slug(storage_slug(title, fallback='audiobook'), taken)}.mp3"
    storage_path = audiobook_object_path(workspace_slug, source_slug, stored_name)
    await storage.upload(
        bucket=bucket,
        path=storage_path,
        content=content,
        content_type=AUDIOBOOK_MIME,
        upsert=False,
        timeout=600,
    )
    payload = {
        "id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "source_id": source_id,
        "production_run_id": None,
        "artifact_type": AUDIOBOOK,
        "format": "mp3",
        "filename": audiobook_filename(title),
        "storage_path": storage_path,
        "file_size_bytes": len(content),
        "manifest": {"title": title, "status": "ready"},
        "origin": {"source": "library_upload"},
    }
    try:
        return await artifacts.create(payload)
    except Exception:
        logger.exception("Failed to save audiobook row for %s", storage_path)
        try:
            await storage.delete(bucket=bucket, path=storage_path)
        except Exception:
            logger.exception("Failed to delete orphaned audiobook at %s", storage_path)
        raise


async def _import_knowledge(
    *,
    workspace_id: str,
    source_id: str,
    title: str,
    filename: str,
    content: bytes,
    max_bytes: int,
    wiki_entries: WikiEntryRepository,
    assessments: AssessmentRepository,
) -> dict[str, int]:
    if len(content) > max_bytes:
        max_megabytes = max_bytes // (1024 * 1024)
        raise LibraryArtifactError(f"Uploaded file exceeds the {max_megabytes} MB limit.")
    try:
        safe_filename = sanitize_upload_filename(filename)
    except SourceUploadValidationError as exc:
        raise LibraryArtifactError(str(exc)) from exc
    if not safe_filename.lower().endswith(".json"):
        raise LibraryArtifactError("Knowledge must be a .json file.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LibraryArtifactError("Knowledge must be valid UTF-8.") from exc
    try:
        notes = require_structured_notes(text, filename=safe_filename)
    except StructuredNotesError as exc:
        raise LibraryArtifactError(str(exc)) from exc

    existing = await wiki_entries.list_for_workspace(workspace_id, status="canonical", limit=1000)
    saved = await _save_wiki_entries(
        workspace_id=workspace_id,
        source_id=source_id,
        title=title,
        notes=notes,
        existing=existing,
        wiki_entries=wiki_entries,
    )
    question_count = 0
    if notes.questions:
        try:
            rows = _imported_question_rows(
                {"workspace_id": workspace_id, "source_id": source_id},
                notes.questions,
                citation_catalog(saved, existing),
            )
        except KnowledgeProjectError as exc:
            raise LibraryArtifactError(str(exc)) from exc
        await assessments.insert_quizzes(rows)
        question_count = len(rows)
    if not saved and question_count == 0:
        raise LibraryArtifactError("The JSON did not contain wiki entries or questions.")
    return {"wiki_entry_count": len(saved), "question_count": question_count}


async def _save_wiki_entries(
    *,
    workspace_id: str,
    source_id: str,
    title: str,
    notes: StructuredNotes,
    existing: list[dict[str, Any]],
    wiki_entries: WikiEntryRepository,
) -> list[dict[str, Any]]:
    if not notes.entries:
        return []
    candidates = _candidates(
        notes,
        source_id,
        knowledge_project_id=None,
        section_title=title,
    )
    inserts, updates, conflicted = promote_candidates(
        workspace_id=workspace_id,
        candidates=candidates,
        existing_entries=existing,
    )
    saved: list[dict[str, Any]] = []
    if inserts:
        saved.extend(await wiki_entries.insert_many(inserts))
    for row in updates:
        entry_id = str(row.pop("id"))
        saved.append(await wiki_entries.update(entry_id, row))
    existing_by_key = {
        (str(entry.get("preferred_label") or "").casefold(), str(entry.get("entry_kind") or "term")): entry
        for entry in existing
    }
    for index in conflicted:
        candidate = candidates[index]
        match = existing_by_key.get((candidate.label.casefold(), candidate.entry_kind))
        if match:
            saved.append(match)
    if not saved and not notes.questions:
        raise LibraryArtifactError(
            "The JSON matched wiki entries that already disagree, so nothing was written.",
        )
    return saved
