"""Wiki knowledge ingest (Foundry production run) and entry management (Academy).

OPS New Run with Wiki Knowledge writes one ``wiki_ingest_batches`` row per
selected source. Attachments point at the existing source file on a
``production_run`` with ``target_artifacts=["wiki_knowledge"]``. The worker
transcribes that file if needed, structures notes, and writes canonical
``wiki_entries``. Academy Library lists those entries; Academy edits,
deprecates, and AI-rewrites them. Ingest-batch HTTP endpoints remain for
API clients.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.artifact_paths import storage_slug
from app.config import Settings, get_settings
from app.intellex.wiki_candidates import WikiCandidate, candidate_slug
from app.models.wiki_ingest import WikiIngestCreate
from app.pipeline import build_pipeline
from app.repositories.production_runs import ProductionRunRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.repositories.wiki_ingest_batches import WikiIngestBatchRepository
from app.services.embeddings import EmbeddingClient, get_embedding_client, to_pgvector_literal
from app.services.llm import get_llm_client
from app.services.llm.base import LLMClient
from app.services.production_runs import ProductionRunEnqueueError
from app.services.queue import enqueue_production_run
from app.services.supabase_storage import SupabaseStorageClient, SupabaseStorageError
from app.services.wiki_transcription import (
    ValidatedAttachment,
    WikiTranscriptionError,
    attachment_storage_path,
    validate_note_attachment,
)

logger = logging.getLogger(__name__)

STRUCTURING_ACTION = "wiki_structuring"
REVISE_ACTION = "wiki_revise"

STRUCTURING_SYSTEM_PROMPT = """You convert a reader's unstructured book notes into structured wiki entries.

The notes are terminology, concepts, and insights the reader wrote down while reading. Your only job is to FORMAT them — never to add knowledge.

Rules:
1. Split, don't summarize. Each atomic term/concept/insight becomes its own entry; compound notes are split.
2. Merge within the batch. Obvious restatements of the same item collapse into one entry (merge their aliases).
3. No invention. Definitions may only rephrase the reader's words — fix grammar and expand shorthand, never add facts the notes don't contain. If a term is named but not defined, use the best available fragment as the definition.
4. Insights keep the reader's voice. Light grammar cleanup only.
5. Classification: vocabulary with a compact definition → "term"; an idea/model/framework → "concept"; a judgment/takeaway/lesson → "insight".
6. importance defaults to "supporting". Use "essential" or "contextual" only when the notes signal it ("key idea", "(minor)", emphasis). Do not inflate importance.
7. aliases: alternate names present in the notes ("aka …", parentheticals, abbreviations).
8. prerequisite_labels: only when the notes explicitly relate entries ("related to X", "builds on Y") — use the other entry's label.
9. pronunciation: only when the notes give one.
10. note_excerpt: a verbatim fragment (max 240 chars) of the notes this entry came from.
11. Anything you cannot confidently structure goes into unparsed_fragments verbatim — never guess it into an entry, never silently drop it.

Respond with a JSON object:
{
  "entries": [
    {
      "label": string,
      "entry_kind": "term" | "concept" | "insight",
      "definition": string,
      "aliases": [string],
      "pronunciation": string | null,
      "importance": "essential" | "supporting" | "contextual",
      "prerequisite_labels": [string],
      "note_excerpt": string
    }
  ],
  "unparsed_fragments": [string]
}"""

REVISE_SYSTEM_PROMPT = """You rewrite one wiki entry according to the user's instruction.

Rewrite the definition (and label/aliases only when the instruction asks). Do not invent facts the current entry does not support unless the instruction supplies them. Keep the same meaning unless the instruction asks to change it. Stay concise.

Respond with a JSON object:
{
  "definition": string,
  "preferred_label": string | null,
  "aliases": [string] | null
}

Use null for preferred_label or aliases when they should stay unchanged.
"""


class WikiAuthoringError(Exception):
    """Invalid input or state; routers map this to 400."""


class WikiIngestNotFoundError(Exception):
    """Batch or entry does not exist in this workspace; routers map this to 404."""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _embedding_text(label: str, definition: str) -> str:
    return f"{label}. {definition}"


class WikiAuthoringService:
    def __init__(
        self,
        *,
        wiki_entries: WikiEntryRepository,
        batches: WikiIngestBatchRepository,
        production_runs: ProductionRunRepository,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
        revise_llm_client: LLMClient | None = None,
        storage: SupabaseStorageClient | None = None,
    ) -> None:
        self.wiki_entries = wiki_entries
        self.batches = batches
        self.production_runs = production_runs
        self.settings = settings or get_settings()
        self._embedding_client = embedding_client
        self._revise_llm_client = revise_llm_client
        self._storage = storage

    @property
    def embedding_client(self) -> EmbeddingClient:
        if self._embedding_client is None:
            self._embedding_client = get_embedding_client()
        return self._embedding_client

    @property
    def revise_llm_client(self) -> LLMClient:
        if self._revise_llm_client is None:
            self._revise_llm_client = get_llm_client(REVISE_ACTION)
        return self._revise_llm_client

    @property
    def storage(self) -> SupabaseStorageClient:
        if self._storage is None:
            self._storage = SupabaseStorageClient(self.settings)
        return self._storage

    async def create_batch(
        self,
        payload: WikiIngestCreate,
        workspace_id: str,
        *,
        owner_id: str,
    ) -> dict[str, Any]:
        notes = payload.notes.strip()
        if not notes:
            raise WikiAuthoringError("Notes are empty.")

        source_id = (payload.source_id or "").strip()
        if not source_id:
            raise WikiAuthoringError("source_id is required.")

        max_chars = self.settings.wiki_authoring.max_notes_chars
        if len(notes) > max_chars:
            raise WikiAuthoringError(
                f"Notes exceed {max_chars} characters. "
                "Split the dump (one chapter per batch works well).",
            )

        chapter = await self._resolve_chapter(payload.chapter_hint, source_id)
        title = (payload.title or "").strip() or f"Notes — {_utc_now_iso()[:10]}"
        return await self._queue_wiki_knowledge_run(
            workspace_id=workspace_id,
            owner_id=owner_id,
            source_id=source_id,
            batch_payload={
                "workspace_id": workspace_id,
                "source_id": source_id,
                "title": title,
                "raw_notes": notes,
                "chapter_hint": payload.chapter_hint,
                "chapter": chapter,
                "status": "transcribed",
                "entries": [],
                "unparsed_fragments": [],
                "attachments": [],
            },
        )

    async def create_file_batch(
        self,
        *,
        workspace_id: str,
        owner_id: str,
        source_id: str,
        chapter_hint: str | None,
        title: str | None,
        files: list[tuple[str, str | None, bytes]],
    ) -> dict[str, Any]:
        if not (source_id or "").strip():
            raise WikiAuthoringError("source_id is required for file ingest.")

        wiki_settings = self.settings.wiki_authoring
        if not files:
            raise WikiAuthoringError("Upload at least one note file.")

        if len(files) > wiki_settings.max_attachments_per_batch:
            raise WikiAuthoringError(
                f"At most {wiki_settings.max_attachments_per_batch} files per batch.",
            )

        validated: list[ValidatedAttachment] = []
        try:
            for order, (filename, content_type, content) in enumerate(files):
                validated.append(
                    validate_note_attachment(
                        order=order,
                        filename=filename,
                        content_type=content_type,
                        content=content,
                        max_bytes=wiki_settings.max_attachment_bytes,
                    ),
                )
        except WikiTranscriptionError as exc:
            raise WikiAuthoringError(str(exc)) from exc

        chapter = await self._resolve_chapter(chapter_hint, source_id)
        workspace = await self.batches.db.select_one(
            "workspaces",
            filters={"id": f"eq.{workspace_id}"},
        )
        if not workspace or not workspace.get("slug"):
            raise WikiAuthoringError("Workspace is missing a storage slug.")
        batch_id = str(uuid.uuid4())
        display_title = (title or "").strip() or f"Notes — {_utc_now_iso()[:10]}"
        batch_slug = storage_slug(display_title, fallback="notes")
        attachments: list[dict[str, Any]] = []
        bucket = self.settings.sources_bucket

        try:
            for item in validated:
                path = attachment_storage_path(
                    workspace_slug=str(workspace["slug"]),
                    batch_slug=batch_slug,
                    order=item.order,
                    filename=item.filename,
                )
                await self.storage.upload(
                    bucket=bucket,
                    path=path,
                    content=item.content,
                    content_type=item.mime_type,
                )
                attachments.append(
                    {
                        "order": item.order,
                        "filename": item.filename,
                        "mime_type": item.mime_type,
                        "storage_path": path,
                        "byte_size": len(item.content),
                    },
                )
        except SupabaseStorageError as exc:
            raise WikiAuthoringError(f"Could not store note files: {exc}") from exc

        return await self._queue_wiki_knowledge_run(
            workspace_id=workspace_id,
            owner_id=owner_id,
            source_id=source_id,
            batch_payload={
                "id": batch_id,
                "workspace_id": workspace_id,
                "source_id": source_id,
                "title": display_title,
                "raw_notes": "",
                "chapter_hint": chapter_hint,
                "chapter": chapter,
                "status": "transcribing",
                "entries": [],
                "unparsed_fragments": [],
                "attachments": attachments,
                "transcription_error": None,
            },
        )

    async def create_entry(
        self,
        workspace_id: str,
        *,
        preferred_label: str,
        definition: str,
        entry_kind: str,
        importance: str,
        aliases: list[str],
        pronunciation: str | None,
        origin: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing_entries = await self._list_all_entries(workspace_id)
        entry_origin = origin if isinstance(origin, dict) and origin.get("kind") else {"kind": "manual"}
        candidate = WikiCandidate(
            label=preferred_label.strip(),
            definition=definition.strip(),
            entry_kind=entry_kind,
            importance=importance,
            aliases=aliases,
            pronunciation=pronunciation,
            origin=entry_origin,
        )
        slug = candidate_slug(candidate, {
            str(entry["canonical_slug"]): entry for entry in existing_entries
        })

        if any(str(entry["canonical_slug"]) == slug for entry in existing_entries):
            raise WikiAuthoringError(
                f"An entry with the slug '{slug}' already exists. Edit it instead.",
            )

        rows = await self.wiki_entries.insert_many(
            [
                {
                    "workspace_id": workspace_id,
                    "preferred_label": candidate.label,
                    "canonical_slug": slug,
                    "definition": candidate.definition,
                    "pronunciation": candidate.pronunciation,
                    "aliases": candidate.aliases,
                    "prerequisites": [],
                    "importance": candidate.importance,
                    "entry_kind": candidate.entry_kind,
                    "status": "canonical",
                    "evidence": [],
                    "origin": candidate.origin,
                },
            ],
        )
        await self._embed_entries([str(rows[0]["id"])])
        return rows[0]

    async def update_entry(
        self,
        wiki_entry_id: str,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = await self.wiki_entries.get_for_workspace(wiki_entry_id, workspace_id)

        if not row:
            raise WikiIngestNotFoundError("Wiki entry not found.")

        updated = await self.wiki_entries.update(wiki_entry_id, payload)

        if "definition" in payload or "preferred_label" in payload:
            await self._embed_entries([wiki_entry_id])
            updated = await self.wiki_entries.get_for_workspace(wiki_entry_id, workspace_id) or updated

        return updated

    async def deprecate_entry(self, wiki_entry_id: str, workspace_id: str) -> dict[str, Any]:
        row = await self.wiki_entries.get_for_workspace(wiki_entry_id, workspace_id)

        if not row:
            raise WikiIngestNotFoundError("Wiki entry not found.")

        return await self.wiki_entries.update(wiki_entry_id, {"status": "deprecated"})

    async def revise_entry(
        self,
        wiki_entry_id: str,
        workspace_id: str,
        instruction: str,
    ) -> dict[str, Any]:
        row = await self.wiki_entries.get_for_workspace(wiki_entry_id, workspace_id)
        if not row:
            raise WikiIngestNotFoundError("Wiki entry not found.")

        stripped = instruction.strip()
        if not stripped:
            raise WikiAuthoringError("Instruction is empty.")

        origin = row.get("origin") if isinstance(row.get("origin"), dict) else {}
        excerpt = str(origin.get("note_excerpt") or "").strip()
        evidence_lines = []
        for record in row.get("evidence") or []:
            if not isinstance(record, dict):
                continue
            quote = str(record.get("quote") or record.get("preview") or "").strip()
            if quote:
                evidence_lines.append(quote)

        user_prompt = (
            f"LABEL: {row.get('preferred_label') or ''}\n"
            f"KIND: {row.get('entry_kind') or ''}\n"
            f"ALIASES: {', '.join(str(alias) for alias in (row.get('aliases') or []) if str(alias).strip()) or '(none)'}\n"
            f"CURRENT DEFINITION:\n{row.get('definition') or ''}\n"
        )
        if excerpt:
            user_prompt += f"\nNOTE EXCERPT:\n{excerpt}\n"
        if evidence_lines:
            user_prompt += "\nEVIDENCE QUOTES:\n" + "\n".join(f"- {line}" for line in evidence_lines) + "\n"
        user_prompt += f"\nINSTRUCTION:\n{stripped}"

        result = await asyncio.to_thread(
            self.revise_llm_client.complete_json,
            system_prompt=REVISE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        definition = str(result.content.get("definition") or "").strip()
        if not definition:
            raise WikiAuthoringError("Revise failed: the model returned an empty definition.")

        label_raw = result.content.get("preferred_label")
        preferred_label = str(label_raw).strip() if label_raw else None
        aliases_raw = result.content.get("aliases")
        aliases: list[str] | None = None
        if isinstance(aliases_raw, list):
            aliases = [str(alias).strip() for alias in aliases_raw if str(alias).strip()]

        return {
            "definition": definition,
            "preferred_label": preferred_label or None,
            "aliases": aliases,
        }

    async def _queue_wiki_knowledge_run(
        self,
        *,
        workspace_id: str,
        owner_id: str,
        source_id: str,
        batch_payload: dict[str, Any],
    ) -> dict[str, Any]:
        run = await self.production_runs.create(
            {
                "workspace_id": workspace_id,
                "owner_id": owner_id,
                "source_ids": [source_id],
                "target_artifacts": ["wiki_knowledge"],
                "pipeline": build_pipeline(["wiki_knowledge"]),
                "status": "queued",
            },
        )
        batch_payload = {**batch_payload, "production_run_id": run["id"]}
        try:
            row = await self.batches.insert(batch_payload)
        except Exception:
            await self.production_runs.update(
                run["id"],
                {
                    "status": "failed",
                    "error": "Failed to store wiki ingest batch.",
                },
            )
            raise

        try:
            enqueue_production_run(self.settings, run["id"])
        except Exception as exc:
            logger.exception("Failed to enqueue wiki knowledge run %s", run["id"])
            await self.production_runs.update(
                run["id"],
                {
                    "status": "failed",
                    "error": f"Failed to enqueue production run: {exc}",
                },
            )
            await self.batches.update(
                str(row["id"]),
                {
                    "status": "failed",
                    "transcription_error": f"Failed to enqueue production run: {exc}",
                },
            )
            raise ProductionRunEnqueueError(str(exc)) from exc

        return row

    async def _resolve_chapter(
        self,
        chapter_hint: str | None,
        source_id: str | None,
    ) -> dict[str, Any] | None:
        if not chapter_hint or not source_id:
            return None

        hint = chapter_hint.strip()
        if not hint:
            return None

        rows = await self.batches.list_chapters_for_source(source_id)

        matched: dict[str, Any] | None = None
        if hint.isdigit():
            wanted = int(hint)
            matched = next(
                (row for row in rows if int(row.get("sequence_index") or -1) == wanted),
                None,
            )

        if matched is None:
            lowered = hint.lower()
            matched = next(
                (row for row in rows if lowered in str(row.get("title") or "").lower()),
                None,
            )

        if matched is None:
            return None

        section_segment_ids = [
            str(segment_id)
            for section in matched.get("sections") or []
            for segment_id in section.get("segment_ids") or []
        ]
        return {
            "chapter_id": str(matched["id"]),
            "title": str(matched.get("title") or "Untitled"),
            "sequence_index": int(matched.get("sequence_index") or 0),
            "segment_ids": [
                *(str(segment_id) for segment_id in matched.get("segment_ids") or []),
                *section_segment_ids,
            ],
        }

    async def _list_all_entries(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.wiki_entries.list_for_workspace(workspace_id, limit=1000)

    async def _embed_entries(self, wiki_entry_ids: list[str]) -> None:
        if not wiki_entry_ids:
            return

        rows = await self.wiki_entries.get_many(wiki_entry_ids)
        if not rows:
            return

        texts = [
            _embedding_text(
                str(row.get("preferred_label") or ""),
                str(row.get("definition") or ""),
            )
            for row in rows
        ]
        vectors = await asyncio.to_thread(self.embedding_client.embed, texts)
        now = _utc_now_iso()

        for row, vector in zip(rows, vectors):
            await self.wiki_entries.update(
                str(row["id"]),
                {"embedding": to_pgvector_literal(vector), "embedded_at": now},
            )
