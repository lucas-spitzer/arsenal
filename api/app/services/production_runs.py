from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.pipeline import build_pipeline
from app.repositories.production_runs import ProductionRunRepository
from app.repositories.wiki_ingest_batches import WikiIngestBatchRepository
from app.services.queue import enqueue_production_run

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
) -> dict[str, Any]:
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
