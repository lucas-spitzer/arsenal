from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.pipeline import build_pipeline
from app.repositories.artifacts import ArtifactRepository
from app.repositories.narration_segments import NarrationSegmentRepository
from app.repositories.production_runs import ProductionRunRepository
from app.repositories.stage_settings import StageSettingsRepository
from app.repositories.wiki_ingest_batches import WikiIngestBatchRepository
from app.services.narration_checkpoint import (
    clear_narration_checkpoints,
    configured_narration_voice,
)
from app.services.queue import cancel_queued_jobs_for_run, enqueue_production_run
from app.services.supabase_storage import SupabaseStorageClient

logger = logging.getLogger(__name__)


class ProductionRunEnqueueError(RuntimeError):
    """Raised when a production run record exists but could not be queued."""


class ProductionRunValidationError(ValueError):
    """Raised when a run cannot be set up from the given sources."""


def _source_wiki_attachment(source: dict[str, Any]) -> dict[str, Any]:
    path = str(source.get("storage_path") or "").strip()
    if not path:
        raise ProductionRunValidationError(
            "Source is missing a storage path; re-upload it before running Wiki Knowledge.",
        )
    return {
        "order": 0,
        "filename": str(source.get("filename") or "notes"),
        "mime_type": str(source.get("mime_type") or "application/octet-stream"),
        "storage_path": path,
        "byte_size": int(source.get("file_size_bytes") or 0),
    }


async def _create_wiki_knowledge_batches(
    *,
    workspace_id: str,
    production_run_id: str,
    source_ids: list[str],
    sources: list[dict[str, Any]],
    batches: WikiIngestBatchRepository,
) -> None:
    by_id = {str(source["id"]): source for source in sources}
    for source_id in source_ids:
        source = by_id.get(source_id)
        if not source:
            raise ProductionRunValidationError(
                f"Source {source_id} was not found for this wiki knowledge run.",
            )
        filename = str(source.get("filename") or "Notes")
        await batches.insert(
            {
                "workspace_id": workspace_id,
                "source_id": source_id,
                "production_run_id": production_run_id,
                "title": filename,
                "raw_notes": "",
                "chapter_hint": None,
                "chapter": None,
                "status": "transcribing",
                "entries": [],
                "unparsed_fragments": [],
                "attachments": [_source_wiki_attachment(source)],
                "transcription_error": None,
            },
        )


async def create_and_enqueue_production_run(
    *,
    workspace_id: str,
    owner_id: str,
    source_ids: list[str],
    target_artifacts: list[str],
    settings: Settings,
    production_runs: ProductionRunRepository,
    sources: list[dict[str, Any]] | None = None,
    batches: WikiIngestBatchRepository | None = None,
    narration_restart_source_ids: list[str] | None = None,
    stage_settings: StageSettingsRepository | None = None,
    narration_segments: NarrationSegmentRepository | None = None,
    artifacts: ArtifactRepository | None = None,
    storage: SupabaseStorageClient | None = None,
) -> dict[str, Any]:
    if any(source.get("source_kind") == "structured_data" for source in sources or []):
        raise ProductionRunValidationError(
            "Structured data sources can't run through the document pipeline.",
        )

    selected_sources = set(source_ids)
    restart_ids = [
        source_id
        for source_id in dict.fromkeys(narration_restart_source_ids or [])
        if source_id in selected_sources
    ]
    if restart_ids and "narration_audio" in target_artifacts:
        if (
            stage_settings is None
            or narration_segments is None
            or artifacts is None
            or storage is None
        ):
            raise ProductionRunValidationError(
                "Restarting narration requires stage settings, narration storage, and artifacts.",
            )
        stage_rows = await stage_settings.list_for_workspace(workspace_id)
        model_id, voice_id = configured_narration_voice(settings, stage_rows)
        await clear_narration_checkpoints(
            workspace_id=workspace_id,
            owner_id=owner_id,
            source_ids=restart_ids,
            model_id=model_id,
            voice_id=voice_id,
            narration_segments=narration_segments,
            artifacts=artifacts,
            storage=storage,
            bucket=settings.sources_bucket,
        )

    pipeline = build_pipeline(target_artifacts)

    row = await production_runs.create(
        {
            "workspace_id": workspace_id,
            "owner_id": owner_id,
            "source_ids": source_ids,
            "target_artifacts": target_artifacts,
            "pipeline": pipeline,
            "status": "queued",
        },
    )

    if "wiki_knowledge" in target_artifacts:
        if batches is None:
            await production_runs.update(
                row["id"],
                {
                    "status": "failed",
                    "error": "Wiki knowledge runs require an ingest-batch repository.",
                },
            )
            raise ProductionRunValidationError(
                "Wiki knowledge runs require an ingest-batch repository.",
            )
        try:
            await _create_wiki_knowledge_batches(
                workspace_id=workspace_id,
                production_run_id=row["id"],
                source_ids=source_ids,
                sources=sources or [],
                batches=batches,
            )
        except Exception as exc:
            logger.exception(
                "Failed to store wiki ingest batches for production run %s",
                row["id"],
            )
            await production_runs.update(
                row["id"],
                {
                    "status": "failed",
                    "error": f"Failed to store wiki ingest batch: {exc}",
                },
            )
            raise

    try:
        enqueue_production_run(settings, row["id"])
    except Exception as exc:
        logger.exception(
            "Failed to enqueue production run %s",
            row["id"],
        )
        await production_runs.update(
            row["id"],
            {
                "status": "failed",
                "error": f"Failed to enqueue production run: {exc}",
            },
        )
        raise ProductionRunEnqueueError(str(exc)) from exc

    return row


def _storage_keys_by_bucket(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        bucket = str(row.get("bucket") or "").strip()
        name = str(row.get("name") or "").strip()
        if not bucket or not name or name == "pending":
            continue
        grouped.setdefault(bucket, []).append(name)
    return grouped


async def purge_production_run(
    *,
    production_run_id: str,
    settings: Settings,
    production_runs: ProductionRunRepository,
    storage: SupabaseStorageClient,
) -> None:
    cancel_queued_jobs_for_run(settings, production_run_id)
    rows = await production_runs.purge(production_run_id)
    for bucket, paths in _storage_keys_by_bucket(rows).items():
        await storage.delete_paths(bucket=bucket, paths=paths)
