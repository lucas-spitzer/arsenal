"""Intellex stages: transcribe wiki note files and write canonical wiki entries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.intellex.wiki_candidates import (
    WikiCandidate,
    promote_candidates,
    resolve_prerequisites,
)
from app.models.wiki_ingest import WikiIngestEntry, WikiIngestEvidence
from app.services.api_pricing import cost_llm_usage
from app.services.embeddings import to_pgvector_literal
from app.services.llm import get_llm_client
from app.services.retrieval import build_reader_link
from app.services.stage_run_billing import stage_run_completion_fields
from app.services.wiki_authoring import STRUCTURING_ACTION, STRUCTURING_SYSTEM_PROMPT
from app.services.wiki_transcription import transcribe_attachments_in_order
from app.worker.db import WorkerDatabase
from app.worker.storage import WorkerStorage

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _embedding_text(label: str, definition: str) -> str:
    return f"{label}. {definition}"


class TranscribeWikiNotesStageExecutor:
    STAGE_ID = "transcribe-wiki-notes"
    STAGE_VERSION = "1.0"
    MODULE = "intellex"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        storage: WorkerStorage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.storage = storage or WorkerStorage()

    def run(self, *, production_run_id: str, workspace_id: str, source_id: str) -> str:
        batch = self.db.get_wiki_ingest_batch_for_run(production_run_id, source_id=source_id)
        if not batch:
            raise RuntimeError(
                f"No wiki ingest batch for production run {production_run_id} source {source_id}.",
            )

        attachments = batch.get("attachments") or []
        notes = str(batch.get("raw_notes") or "").strip()
        skip = bool(notes) or not isinstance(attachments, list) or not attachments

        stage_run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": {
                    "batch_id": batch["id"],
                    "attachment_count": len(attachments) if isinstance(attachments, list) else 0,
                    "skipped": skip,
                },
                "started_at": utc_now_iso(),
            },
        )
        stage_run_id = stage_run["id"]

        try:
            if skip:
                self.db.update_stage_run(
                    stage_run_id,
                    {
                        "status": "completed",
                        "output": {
                            "skipped": True,
                            "attachment_count": 0,
                            "raw_notes_chars": len(notes),
                        },
                        **stage_run_completion_fields(
                            {"model": "deterministic-passthrough", "token_usage": {}},
                        ),
                        "completed_at": utc_now_iso(),
                    },
                )
                return stage_run_id

            items: list[tuple[dict[str, Any], bytes]] = []
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    raise RuntimeError("Attachment metadata is invalid.")
                path = str(attachment.get("storage_path") or "")
                if not path:
                    raise RuntimeError("Attachment is missing storage_path.")
                items.append((attachment, self.storage.download(path)))

            raw_notes = transcribe_attachments_in_order(items)
            self.db.update_wiki_ingest_batch(
                str(batch["id"]),
                {
                    "status": "transcribed",
                    "raw_notes": raw_notes,
                    "transcription_error": None,
                },
            )
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": {
                        "skipped": False,
                        "attachment_count": len(items),
                        "raw_notes_chars": len(raw_notes),
                    },
                    **stage_run_completion_fields(
                        {"model": "llamaparse", "token_usage": {}},
                    ),
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id
        except Exception as exc:
            logger.exception("Wiki note transcription failed for run %s", production_run_id)
            self.db.update_wiki_ingest_batch(
                str(batch["id"]),
                {
                    "status": "failed",
                    "transcription_error": (str(exc) or exc.__class__.__name__)[:2000],
                },
            )
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "failed",
                    "error": str(exc) or exc.__class__.__name__,
                    "completed_at": utc_now_iso(),
                },
            )
            raise


class StructureWikiNotesStageExecutor:
    STAGE_ID = "structure-wiki-notes"
    STAGE_VERSION = "1.0"
    MODULE = "intellex"

    def __init__(self, db: WorkerDatabase | None = None) -> None:
        self.db = db or WorkerDatabase()

    def run(self, *, production_run_id: str, workspace_id: str, source_id: str) -> str:
        batch = self.db.get_wiki_ingest_batch_for_run(production_run_id, source_id=source_id)
        if not batch:
            raise RuntimeError(
                f"No wiki ingest batch for production run {production_run_id} source {source_id}.",
            )

        notes = str(batch.get("raw_notes") or "").strip()
        stage_run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": {"batch_id": batch["id"], "note_chars": len(notes)},
                "started_at": utc_now_iso(),
            },
        )
        stage_run_id = stage_run["id"]

        try:
            if not notes:
                raise RuntimeError("Wiki notes are empty after transcription.")

            max_chars = get_settings().wiki_authoring.max_notes_chars
            if len(notes) > max_chars:
                raise RuntimeError(f"Notes exceed {max_chars} characters.")

            self.db.update_wiki_ingest_batch(
                str(batch["id"]),
                {"status": "structuring", "transcription_error": None},
            )

            chapter = batch.get("chapter") if isinstance(batch.get("chapter"), dict) else {}
            chapter_title = str(chapter.get("title") or "") if chapter else ""
            context = f"These notes are from the chapter: {chapter_title}\n\n" if chapter_title else ""
            client = get_llm_client(STRUCTURING_ACTION)
            result = client.complete_json(
                system_prompt=STRUCTURING_SYSTEM_PROMPT,
                user_prompt=f"{context}READER NOTES:\n{notes}",
            )
            raw_entries = result.content.get("entries")
            if not isinstance(raw_entries, list) or not raw_entries:
                raise RuntimeError("Structuring failed: the model returned no entries.")

            fragments = result.content.get("unparsed_fragments")
            unparsed = [
                str(fragment)
                for fragment in (fragments if isinstance(fragments, list) else [])
                if str(fragment).strip()
            ]
            entries = _parse_entries(raw_entries)
            if not entries:
                raise RuntimeError("Structuring failed: no usable entries.")

            source_id = str(batch.get("source_id") or "") or None
            _attach_evidence(
                self.db,
                entries,
                workspace_id=workspace_id,
                source_id=source_id,
                chapter=chapter if isinstance(chapter, dict) else {},
            )

            existing = self.db.list_wiki_entries_for_workspace(workspace_id)
            candidates = [
                _entry_to_candidate(
                    entry,
                    batch_id=str(batch["id"]),
                    production_run_id=production_run_id,
                    stage_run_id=stage_run_id,
                    source_id=source_id,
                    chapter=chapter if isinstance(chapter, dict) else {},
                )
                for entry in entries
            ]
            inserts, updates, _conflicted = promote_candidates(
                workspace_id=workspace_id,
                candidates=candidates,
                existing_entries=existing,
                override_conflicts=True,
            )
            inserted_rows = self.db.insert_wiki_entries(inserts) if inserts else []
            updated_ids: list[str] = []
            for update in updates:
                payload = dict(update)
                wiki_id = str(payload.pop("id"))
                self.db.update_wiki_entry(wiki_id, payload)
                updated_ids.append(wiki_id)

            all_rows = self.db.list_wiki_entries_for_workspace(workspace_id)
            for prereq_update in resolve_prerequisites(candidates=candidates, wiki_rows=all_rows):
                payload = dict(prereq_update)
                wiki_id = str(payload.pop("id"))
                self.db.update_wiki_entry(wiki_id, payload)

            inserted_ids = [str(row["id"]) for row in inserted_rows]
            self._embed_entries(inserted_ids + updated_ids)

            usage = result.token_usage or {}
            cost = cost_llm_usage(
                provider=getattr(result, "provider", "openai") or "openai",
                model=result.model,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            )
            self.db.update_wiki_ingest_batch(
                str(batch["id"]),
                {
                    "status": "committed",
                    "entries": [entry.model_dump() for entry in entries],
                    "unparsed_fragments": unparsed,
                    "model": result.model,
                    "cost_usd": cost.get("cost_usd"),
                    "committed_entry_ids": inserted_ids + updated_ids,
                    "committed_at": utc_now_iso(),
                },
            )
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": {
                        "entry_count": len(entries),
                        "inserted_ids": inserted_ids,
                        "updated_ids": updated_ids,
                        "unparsed_fragments": unparsed,
                    },
                    **stage_run_completion_fields(
                        {
                            "model": result.model,
                            "provider": getattr(result, "provider", "openai") or "openai",
                            "token_usage": usage,
                        },
                    ),
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id
        except Exception as exc:
            logger.exception("Wiki note structuring failed for run %s", production_run_id)
            self.db.update_wiki_ingest_batch(
                str(batch["id"]),
                {
                    "status": "failed",
                    "transcription_error": (str(exc) or exc.__class__.__name__)[:2000],
                },
            )
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "failed",
                    "error": str(exc) or exc.__class__.__name__,
                    "completed_at": utc_now_iso(),
                },
            )
            raise

    def _embed_entries(self, wiki_entry_ids: list[str]) -> None:
        if not wiki_entry_ids:
            return
        rows = self.db.get_wiki_entries(wiki_entry_ids)
        if not rows:
            return
        texts = [
            _embedding_text(
                str(row.get("preferred_label") or ""),
                str(row.get("definition") or ""),
            )
            for row in rows
        ]
        try:
            vectors = self.db.embedding_client.embed(texts)
        except Exception:  # noqa: BLE001 - embedding is non-critical
            logger.warning("Wiki entry embed-on-write failed.", exc_info=True)
            return
        now = utc_now_iso()
        for row, vector in zip(rows, vectors):
            self.db.update_wiki_entry(
                str(row["id"]),
                {"embedding": to_pgvector_literal(vector), "embedded_at": now},
            )


def _parse_entries(raw_entries: list[Any]) -> list[WikiIngestEntry]:
    entries: list[WikiIngestEntry] = []
    allowed_kinds = {"term", "concept", "insight"}
    allowed_importance = {"essential", "supporting", "contextual"}
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "").strip()
        definition = str(raw.get("definition") or "").strip()
        if not label or not definition:
            continue
        kind = str(raw.get("entry_kind") or "").strip().lower()
        importance = str(raw.get("importance") or "").strip().lower()
        entries.append(
            WikiIngestEntry(
                index=len(entries),
                label=label[:120],
                entry_kind=kind if kind in allowed_kinds else "concept",
                definition=definition,
                aliases=[str(alias) for alias in raw.get("aliases") or [] if str(alias).strip()],
                pronunciation=(str(raw["pronunciation"]) if raw.get("pronunciation") else None),
                importance=importance if importance in allowed_importance else "supporting",
                prerequisite_labels=[
                    str(item) for item in raw.get("prerequisite_labels") or [] if str(item).strip()
                ],
                note_excerpt=str(raw.get("note_excerpt") or "")[:240],
            ),
        )
    return entries


def _attach_evidence(
    db: WorkerDatabase,
    entries: list[WikiIngestEntry],
    *,
    workspace_id: str,
    source_id: str | None,
    chapter: dict[str, Any],
) -> None:
    if not source_id or not entries:
        return
    settings = get_settings().wiki_authoring
    texts = [_embedding_text(entry.label, entry.definition) for entry in entries]
    try:
        vectors = db.embedding_client.embed(texts)
    except Exception:  # noqa: BLE001 - evidence is best-effort
        logger.warning("Wiki evidence embed failed.", exc_info=True)
        return

    chapter_segment_ids = {str(segment_id) for segment_id in chapter.get("segment_ids") or []}
    fetch_count = settings.evidence_top_k * 4 if chapter_segment_ids else settings.evidence_top_k

    for entry, vector in zip(entries, vectors):
        rows = db.match_ndr_segments(
            embedding=vector,
            workspace_id=workspace_id,
            threshold=settings.evidence_weak_floor,
            count=fetch_count,
            source_ids=[source_id],
        )
        if chapter_segment_ids:
            scoped = [row for row in rows if str(row.get("id")) in chapter_segment_ids]
            rows = scoped or rows
        rows = rows[: settings.evidence_top_k]
        entry.evidence = [
            WikiIngestEvidence(
                segment_id=str(row["id"]),
                sequence_index=row.get("sequence_index"),
                page=(row.get("locator") or {}).get("page") if isinstance(row.get("locator"), dict) else None,
                similarity=round(float(row.get("similarity") or 0.0), 4),
                preview=str(row.get("text") or "")[:280],
                reader_link=build_reader_link(
                    str(row.get("source_id") or source_id),
                    int(row.get("sequence_index") or 0),
                ),
            )
            for row in rows
        ]
        best = max((float(row.get("similarity") or 0.0) for row in rows), default=0.0)
        if best >= settings.evidence_threshold:
            entry.evidence_status = "linked"
        elif entry.evidence:
            entry.evidence_status = "weak"
        else:
            entry.evidence_status = "unlinked"


def _entry_to_candidate(
    entry: WikiIngestEntry,
    *,
    batch_id: str,
    production_run_id: str,
    stage_run_id: str,
    source_id: str | None,
    chapter: dict[str, Any],
) -> WikiCandidate:
    evidence: list[dict[str, Any]] = []
    if source_id:
        for record in entry.evidence:
            evidence.append(
                {
                    "source_id": source_id,
                    "segment_id": record.segment_id,
                    "sequence_index": record.sequence_index,
                    "page": record.page,
                    "reader_link": record.reader_link,
                },
            )
    origin: dict[str, Any] = {
        "kind": "wiki_ingest",
        "batch_id": batch_id,
        "production_run_id": production_run_id,
        "stage_run_id": stage_run_id,
        "note_excerpt": entry.note_excerpt,
    }
    if source_id:
        origin["source_id"] = source_id
    if chapter.get("chapter_id"):
        origin["chapter_id"] = chapter["chapter_id"]
    if chapter.get("sequence_index") is not None:
        origin["chapter_sequence_index"] = chapter["sequence_index"]
    return WikiCandidate(
        label=entry.label,
        definition=entry.definition,
        entry_kind=entry.entry_kind,
        aliases=entry.aliases,
        prerequisite_labels=entry.prerequisite_labels,
        pronunciation=entry.pronunciation,
        importance=entry.importance,
        evidence=evidence,
        origin=origin,
    )
