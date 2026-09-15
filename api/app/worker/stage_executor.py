from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.artifact_paths import (
    OUTPUT_FILENAMES,
    downloadable_artifact_path,
    pages_work_path,
    parse_work_path,
)
from app.config import get_settings
from app.intellex.models import ParsedDocument
from app.intellex.stages.parse_document import ParseStage
from app.intellex.stages.promotion import (
    merge_research_into_source_metadata,
    merge_web_enrichment_into_source_metadata,
)
from app.intellex.stages.source_research import SourceResearchStage
from app.intellex.stages.web_enrichment import WebEnrichmentStage
from app.intellex.source_readiness import source_intellex_complete
from app.services.api_pricing import cost_web_search_usage
from app.mathesys.stages.wiki_export import build_wiki_export
from app.qngen.assessment_promotion import (
    promote_flashcards,
    promote_quizzes,
    promote_scenarios,
)
from app.qngen.canonical_context import (
    batch_concepts,
    build_source_concepts,
    chapters_from_document_chapters,
)
from app.qngen.stages.flashcard_gen import FlashcardGenStage
from app.qngen.stages.quiz_gen import QuizGenStage
from app.qngen.stages.scenario_gen import ScenarioGenStage
from app.services.stage_run_billing import stage_run_completion_fields
from app.worker.db import WorkerDatabase
from app.worker.storage import WorkerStorage

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SourceResearchStageExecutor:
    STAGE_ID = "source-research"
    STAGE_VERSION = "2.1"
    MODULE = "intellex"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        stage: SourceResearchStage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.stage = stage or SourceResearchStage()

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
        parsed_document: ParsedDocument,
    ) -> str:
        source_id = source["id"]
        stage_run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": {
                    "source_id": source_id,
                    "filename": source.get("filename"),
                    "mime_type": source.get("mime_type"),
                    "page_count": parsed_document.page_count,
                },
                "started_at": utc_now_iso(),
            },
        )
        stage_run_id = stage_run["id"]

        try:
            output, execution = self.stage.run(
                filename=str(source.get("filename") or ""),
                mime_type=str(source.get("mime_type") or ""),
                parsed_document=parsed_document,
            )
            researched_at = utc_now_iso()
            existing_metadata = source.get("source_metadata") or {}
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}

            updated_metadata = merge_research_into_source_metadata(
                existing_metadata,
                output,
                researched_at=researched_at,
            )

            self.db.update_source(
                source_id,
                {
                    "source_metadata": updated_metadata,
                },
            )
            source["source_metadata"] = updated_metadata

            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": output.model_dump(),
                    "promoted": {
                        "source_ids": [source_id],
                        "metadata_namespace": "research",
                    },
                    **stage_run_completion_fields(execution),
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id
        except Exception as exc:
            logger.exception("Stage run %s failed", stage_run_id)
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "completed_at": utc_now_iso(),
                },
            )
            raise


class WebEnrichmentStageExecutor:
    STAGE_ID = "web-enrichment"
    STAGE_VERSION = "1.0"
    MODULE = "intellex"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        stage: WebEnrichmentStage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.stage = stage or WebEnrichmentStage()

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
    ) -> str:
        source_id = source["id"]
        existing_metadata = source.get("source_metadata") or {}
        if not isinstance(existing_metadata, dict):
            existing_metadata = {}

        research = existing_metadata.get("research")
        if not isinstance(research, dict) or not research.get("researched_at"):
            raise RuntimeError(
                f"Source {source_id} has no research metadata; "
                "source-research must run before web-enrichment.",
            )

        stage_run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": {
                    "source_id": source_id,
                    "filename": source.get("filename"),
                    "title": research.get("title"),
                    "identifier": research.get("identifier"),
                },
                "started_at": utc_now_iso(),
            },
        )
        stage_run_id = stage_run["id"]

        try:
            output, execution = self.stage.run(
                filename=str(source.get("filename") or ""),
                research=research,
            )
            enriched_at = utc_now_iso()

            updated_metadata = merge_web_enrichment_into_source_metadata(
                existing_metadata,
                output,
                enriched_at=enriched_at,
            )

            self.db.update_source(
                source_id,
                {
                    "source_metadata": updated_metadata,
                },
            )
            source["source_metadata"] = updated_metadata

            search_count = int(execution.get("search_count") or 0)
            extra_calls = (
                [
                    cost_web_search_usage(
                        provider=str(execution.get("provider") or "anthropic"),
                        search_count=search_count,
                    ),
                ]
                if search_count
                else None
            )

            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": output.model_dump(),
                    "promoted": {
                        "source_ids": [source_id],
                        "metadata_namespace": "web_enrichment",
                    },
                    **stage_run_completion_fields(execution, extra_calls=extra_calls),
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id
        except Exception as exc:
            logger.exception("Stage run %s failed", stage_run_id)
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "completed_at": utc_now_iso(),
                },
            )
            raise


class ParseStageExecutor:
    STAGE_ID = "parse"
    STAGE_VERSION = "1.0"
    MODULE = "intellex"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        storage: WorkerStorage | None = None,
        stage: ParseStage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.storage = storage or WorkerStorage()
        self.stage = stage or ParseStage()

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
        content: bytes,
    ) -> tuple[str, ParsedDocument, list[dict[str, Any]]]:
        source_id = source["id"]
        stage_run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": {
                    "source_id": source_id,
                    "filename": source.get("filename"),
                    "mime_type": source.get("mime_type"),
                    "file_size_bytes": len(content),
                },
                "started_at": utc_now_iso(),
            },
        )
        stage_run_id = stage_run["id"]

        try:
            output, execution = self.stage.run(
                mime_type=source.get("mime_type", ""),
                filename=source.get("filename", ""),
                content=content,
            )
            raw_markdown_path = parse_work_path(source)
            self.storage.upload(
                raw_markdown_path,
                output.raw_markdown.encode("utf-8"),
                bucket=self.storage.sources_bucket,
                content_type="text/markdown",
            )

            structured_path = pages_work_path(source)
            self.storage.upload(
                structured_path,
                json.dumps({"pages": output.structured_pages}, ensure_ascii=False).encode("utf-8"),
                bucket=self.storage.sources_bucket,
                content_type="application/json",
            )

            existing_metadata = source.get("source_metadata") or {}
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}

            parse_metadata = {
                **output.document.to_parse_metadata(),
                "parsed_at": utc_now_iso(),
                "raw_markdown_path": raw_markdown_path,
                "structured_pages_path": structured_path,
                "structured_page_count": len(output.structured_pages),
            }
            updated_metadata = {
                **existing_metadata,
                "parse": parse_metadata,
            }

            self.db.update_source(
                source_id,
                {
                    "status": "processing",
                    "source_metadata": updated_metadata,
                },
            )
            source["source_metadata"] = updated_metadata

            stage_output = output.to_stage_output(raw_markdown_path=raw_markdown_path)
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": stage_output,
                    "promoted": {
                        "source_ids": [source_id],
                        "metadata_namespace": "parse",
                    },
                    **stage_run_completion_fields(execution),
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id, output.document, output.structured_pages
        except Exception as exc:
            logger.exception("Stage run %s failed", stage_run_id)
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "completed_at": utc_now_iso(),
                },
            )
            raise


class ExportWikiJsonStageExecutor:
    """Snapshot the source's curated canonical wiki entries to a JSON artifact.

    Deterministic (no LLM): the curation already happened in the wiki authoring
    flow; this stage makes that knowledge a downloadable Mathesys output.
    """

    STAGE_ID = "export-wiki-json"
    STAGE_VERSION = "1.0"
    MODULE = "mathesys"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        storage: WorkerStorage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.storage = storage or WorkerStorage()

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
    ) -> str:
        source_id = source["id"]
        wiki_entries = self.db.list_wiki_entries_for_workspace(workspace_id)

        stage_run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": {
                    "source_id": source_id,
                    "entry_count": len(
                        [
                            entry
                            for entry in wiki_entries
                            if entry.get("status") == "canonical"
                        ],
                    ),
                },
                "started_at": utc_now_iso(),
            },
        )
        stage_run_id = stage_run["id"]

        try:
            export = build_wiki_export(
                wiki_entries=wiki_entries,
                workspace_id=workspace_id,
                source_id=source_id,
                source_filename=source.get("filename"),
            )
            file_bytes = json.dumps(export, indent=2, ensure_ascii=False).encode("utf-8")

            filename = OUTPUT_FILENAMES["wiki_json"]
            manifest = {
                "export_version": export["arsenal_wiki_export"],
                "entry_count": export["entry_count"],
                "entry_kind_counts": export["entry_kind_counts"],
                "scope_counts": export["scope_counts"],
            }

            artifact_row = self.db.create_artifact(
                {
                    "workspace_id": workspace_id,
                    "source_id": source_id,
                    "production_run_id": production_run_id,
                    "artifact_type": "wiki_json",
                    "format": "json",
                    "filename": filename,
                    "storage_path": "pending",
                    "file_size_bytes": 0,
                    "manifest": manifest,
                    "origin": {
                        "stage_run_id": stage_run_id,
                        "stage_id": self.STAGE_ID,
                        "stage_version": self.STAGE_VERSION,
                    },
                },
            )
            artifact_id = artifact_row["id"]
            storage_path = downloadable_artifact_path(source, "wiki_json")

            self.storage.upload(
                storage_path,
                file_bytes,
                bucket=self.storage.sources_bucket,
                content_type="application/json",
            )

            self.db.update_artifact(
                artifact_id,
                {
                    "storage_path": storage_path,
                    "file_size_bytes": len(file_bytes),
                },
            )

            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": {
                        "files": [
                            {
                                "artifact_id": artifact_id,
                                "filename": filename,
                                "storage_path": storage_path,
                            },
                        ],
                        "entry_count": export["entry_count"],
                        "entry_kind_counts": export["entry_kind_counts"],
                    },
                    "promoted": {"artifact_ids": [artifact_id]},
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id
        except Exception as exc:
            logger.exception("Stage run %s failed", stage_run_id)
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "completed_at": utc_now_iso(),
                },
            )
            raise


class FlashcardGenStageExecutor:
    STAGE_ID = "generate-flashcards"
    STAGE_VERSION = "2.1"
    MODULE = "qngen"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        stage: FlashcardGenStage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.stage = stage or FlashcardGenStage()

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
    ) -> str:
        return _run_qngen_stage(
            db=self.db,
            stage=self.stage,
            stage_id=self.STAGE_ID,
            stage_version=self.STAGE_VERSION,
            module=self.MODULE,
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            source=source,
            promote_items=lambda **kwargs: promote_flashcards(
                flashcards=kwargs["items"],
                workspace_id=kwargs["workspace_id"],
                source_id=kwargs["source_id"],
                production_run_id=kwargs["production_run_id"],
                stage_run_id=kwargs["stage_run_id"],
                stage_id=kwargs["stage_id"],
                stage_version=kwargs["stage_version"],
            ),
            insert_rows=self.db.insert_flashcards,
            output_key="flashcards",
            promoted_key="flashcard_ids",
        )


class QuizGenStageExecutor:
    STAGE_ID = "generate-questions"
    STAGE_VERSION = "2.1"
    MODULE = "qngen"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        stage: QuizGenStage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.stage = stage or QuizGenStage()

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
    ) -> str:
        return _run_qngen_stage(
            db=self.db,
            stage=self.stage,
            stage_id=self.STAGE_ID,
            stage_version=self.STAGE_VERSION,
            module=self.MODULE,
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            source=source,
            promote_items=lambda **kwargs: promote_quizzes(
                questions=kwargs["items"],
                workspace_id=kwargs["workspace_id"],
                source_id=kwargs["source_id"],
                production_run_id=kwargs["production_run_id"],
                stage_run_id=kwargs["stage_run_id"],
                stage_id=kwargs["stage_id"],
                stage_version=kwargs["stage_version"],
            ),
            insert_rows=self.db.insert_quizzes,
            output_key="questions",
            promoted_key="quiz_ids",
        )


class ScenarioGenStageExecutor:
    STAGE_ID = "generate-scenarios"
    STAGE_VERSION = "2.1"
    MODULE = "qngen"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        stage: ScenarioGenStage | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.stage = stage or ScenarioGenStage()

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
    ) -> str:
        return _run_qngen_stage(
            db=self.db,
            stage=self.stage,
            stage_id=self.STAGE_ID,
            stage_version=self.STAGE_VERSION,
            module=self.MODULE,
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            source=source,
            promote_items=lambda **kwargs: promote_scenarios(
                scenarios=kwargs["items"],
                workspace_id=kwargs["workspace_id"],
                source_id=kwargs["source_id"],
                production_run_id=kwargs["production_run_id"],
                stage_run_id=kwargs["stage_run_id"],
                stage_id=kwargs["stage_id"],
                stage_version=kwargs["stage_version"],
            ),
            insert_rows=self.db.insert_scenarios,
            output_key="scenarios",
            promoted_key="scenario_ids",
        )


def _run_qngen_stage(
    *,
    db: WorkerDatabase,
    stage: Any,
    stage_id: str,
    stage_version: str,
    module: str,
    production_run_id: str,
    workspace_id: str,
    source: dict[str, Any],
    promote_items: Any,
    insert_rows: Any,
    output_key: str,
    promoted_key: str,
) -> str:
    source_id = source["id"]
    segments = db.list_ndr_segments_for_source(source_id)

    if not segments:
        raise RuntimeError(f"No NDR segments found for source {source_id}.")

    if not source_intellex_complete(source, has_segments=True):
        raise RuntimeError(
            f"Source {source_id} is not intellex-complete. "
            "Run ingest before generating assessments.",
        )

    wiki_entries = db.list_wiki_entries_for_workspace(workspace_id)
    concepts = build_source_concepts(
        wiki_entries=wiki_entries,
        source_id=source_id,
        segments=segments,
    )

    if not concepts:
        raise RuntimeError(
            f"No canonical wiki entries with evidence found for source {source_id}. "
            "Run Wiki Knowledge from OPS, then review entries in Academy Library "
            "before generating assessments.",
        )

    settings = get_settings()
    concept_batches = batch_concepts(
        concepts,
        batch_size=settings.qngen_concept_batch_size,
    )

    stage_run = db.create_stage_run(
        {
            "production_run_id": production_run_id,
            "workspace_id": workspace_id,
            "stage_id": stage_id,
            "stage_version": stage_version,
            "module": module,
            "status": "running",
            "inputs": {
                "source_id": source_id,
                "segment_count": len(segments),
                "concept_count": len(concepts),
                "wiki_entry_count": len(
                    [entry for entry in wiki_entries if entry.get("status") == "canonical"],
                ),
            },
            "started_at": utc_now_iso(),
        },
    )
    stage_run_id = stage_run["id"]

    try:
        source_metadata = source.get("source_metadata") or {}
        if not isinstance(source_metadata, dict):
            source_metadata = {}

        # Chapter structure comes straight from document_chapters (persisted by
        # the structuring/chunk stages), so QnGen's chapter blueprint has no
        # dependency on the retired extraction stage. Objectives are empty for
        # curated sources; the blueprint runner tolerates that and stages fall
        # back to concept fan-out when the blueprint yields nothing.
        chapter_rows = db.list_document_chapters_for_source(source_id)
        chapters = chapters_from_document_chapters(chapter_rows)

        output, execution = stage.run(
            source_metadata=source_metadata,
            concepts=concepts,
            concept_batches=concept_batches,
            learning_objectives=[],
            chapters=chapters,
        )
        output_data = output.model_dump()
        items = output_data[output_key]

        if execution.get("validation_report"):
            output_data["validation_report"] = execution["validation_report"]

        rows = promote_items(
            items=items,
            workspace_id=workspace_id,
            source_id=source_id,
            production_run_id=production_run_id,
            stage_run_id=stage_run_id,
            stage_id=stage_id,
            stage_version=stage_version,
        )
        created_rows = insert_rows(rows)
        promoted_ids = [str(row["id"]) for row in created_rows]

        db.update_stage_run(
            stage_run_id,
            {
                "status": "completed",
                "output": output_data,
                "promoted": {promoted_key: promoted_ids},
                **stage_run_completion_fields(execution),
                "completed_at": utc_now_iso(),
            },
        )
        return stage_run_id
    except Exception as exc:
        logger.exception("Stage run %s failed", stage_run_id)
        db.update_stage_run(
            stage_run_id,
            {
                "status": "failed",
                "error": str(exc),
                "completed_at": utc_now_iso(),
            },
        )
        raise
