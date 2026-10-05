"""Stage executors for the structure-based document pipeline.

These five executors replace the old prepare-document, deconstruct-document, and
elevenreader-ebook executors. They follow the same pattern as the existing
executors in app/worker/stage_executor.py: create a stage_run row, do the work,
write a metadata namespace + stage_run output, return the stage_run id (and, for
stages whose output the next stage needs, the output object).

All five are deterministic, so they report model="deterministic-passthrough"
(like the old ElevenReader EBook stage) and incur no token cost.

Intermediate artifacts (normalized / trimmed / structure JSON) are persisted to
the sources bucket for auditability and so Create EBook and re-runs can reload
the Book without recomputing it.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.artifact_paths import (
    OUTPUT_FILENAMES,
    book_work_path,
    downloadable_artifact_path,
    normalized_work_path,
    trimmed_work_path,
)
from app.intellex.source_readiness import CURRENT_STRUCTURE_VERSION
from app.intellex.structuring.boundaries import auto_boundaries, trim
from app.intellex.structuring.classify import classify
from app.intellex.structuring.models import (
    Book,
    Element,
    book_from_dict,
)
from app.intellex.structuring.normalize import normalize_structured_pages
from app.intellex.structuring.validate import pdf_text_layer, validate_against_pdf
from app.mathesys.epub_builder import build_epub
from app.mathesys.structured_epub import book_to_epub_chapters
from app.services.stage_run_billing import stage_run_completion_fields
from app.worker.db import WorkerDatabase
from app.worker.storage import WorkerStorage

logger = logging.getLogger(__name__)

_PASSTHROUGH = {"model": "deterministic-passthrough", "token_usage": {}}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _elements_to_json(elements: list[Element]) -> bytes:
    return json.dumps([e.to_dict() for e in elements], ensure_ascii=False).encode("utf-8")


class _ExecutorBase:
    STAGE_ID: str
    STAGE_VERSION: str
    MODULE = "intellex"

    def __init__(self, db: WorkerDatabase | None = None, storage: WorkerStorage | None = None) -> None:
        self.db = db or WorkerDatabase()
        self.storage = storage or WorkerStorage()

    def _start(self, *, production_run_id: str, workspace_id: str, inputs: dict[str, Any]) -> str:
        run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": inputs,
                "started_at": utc_now_iso(),
            }
        )
        return run["id"]

    def _complete(self, stage_run_id: str, *, output: dict[str, Any], promoted: dict[str, Any]) -> None:
        self.db.update_stage_run(
            stage_run_id,
            {
                "status": "completed",
                "output": output,
                "promoted": promoted,
                **stage_run_completion_fields(_PASSTHROUGH),
                "completed_at": utc_now_iso(),
            },
        )

    def _fail(self, stage_run_id: str, exc: Exception) -> None:
        logger.exception("Stage run %s failed", stage_run_id)
        self.db.update_stage_run(
            stage_run_id,
            {"status": "failed", "error": str(exc), "completed_at": utc_now_iso()},
        )

    def _merge_metadata(self, source: dict[str, Any], namespace: str, value: dict[str, Any]) -> None:
        existing = source.get("source_metadata") or {}
        if not isinstance(existing, dict):
            existing = {}
        updated = {**existing, namespace: value}
        self.db.update_source(source["id"], {"source_metadata": updated})
        source["source_metadata"] = updated


class NormalizeStageExecutor(_ExecutorBase):
    """Stage: NORMALIZE -- flatten LlamaParse items, drop headers/footers."""

    STAGE_ID = "normalize-document"
    STAGE_VERSION = "1.1"

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
        structured_pages: list[dict[str, Any]],
    ) -> tuple[str, list[Element]]:
        stage_run_id = self._start(
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            inputs={"source_id": source["id"], "page_count": len(structured_pages)},
        )
        try:
            elements, dropped = normalize_structured_pages(structured_pages)
            path = normalized_work_path(source)
            self.storage.upload(
                path, _elements_to_json(elements),
                bucket=self.storage.sources_bucket, content_type="application/json",
            )
            self._merge_metadata(source, "normalize", {
                "normalized_at": utc_now_iso(),
                "element_count": len(elements),
                "dropped_furniture": dropped,
                "normalized_path": path,
            })
            self._complete(
                stage_run_id,
                output={"element_count": len(elements), "dropped_furniture": dropped},
                promoted={"source_ids": [source["id"]], "metadata_namespace": "normalize"},
            )
            return stage_run_id, elements
        except Exception as exc:
            self._fail(stage_run_id, exc)
            raise


class TrimBoundariesStageExecutor(_ExecutorBase):
    """Stage: TRIM -- drop front/back matter."""

    STAGE_ID = "trim-document-boundaries"
    STAGE_VERSION = "1.0"

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
        elements: list[Element],
    ) -> tuple[str, list[Element]]:
        stage_run_id = self._start(
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            inputs={"source_id": source["id"], "element_count": len(elements)},
        )
        try:
            start_i, end_i, reasons = auto_boundaries(elements)
            if start_i is None:
                start_i = elements[0].index if elements else 0
                reasons = {
                    **reasons,
                    "start": "no division markers; kept from start of document",
                }
            if end_i is None:
                end_i = elements[-1].index + 1 if elements else start_i
            trimmed = trim(elements, start_index=start_i, end_index=end_i)
            path = trimmed_work_path(source)
            self.storage.upload(
                path, _elements_to_json(trimmed),
                bucket=self.storage.sources_bucket, content_type="application/json",
            )
            self._merge_metadata(source, "trim", {
                "trimmed_at": utc_now_iso(),
                "start_index": start_i,
                "end_index": end_i,
                "kept_element_count": len(trimmed),
                "boundary_reasons": reasons,
                "trimmed_path": path,
            })
            self._complete(
                stage_run_id,
                output={"start_index": start_i, "end_index": end_i,
                        "kept_element_count": len(trimmed), "boundary_reasons": reasons},
                promoted={"source_ids": [source["id"]], "metadata_namespace": "trim"},
            )
            return stage_run_id, trimmed
        except Exception as exc:
            self._fail(stage_run_id, exc)
            raise


class StructureStageExecutor(_ExecutorBase):
    """Stage: STRUCTURE -- classify into chapters/sections/body (replaces deconstruct)."""

    STAGE_ID = "structure-document"
    STAGE_VERSION = CURRENT_STRUCTURE_VERSION

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
        trimmed_elements: list[Element],
    ) -> tuple[str, Book]:
        stage_run_id = self._start(
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            inputs={"source_id": source["id"], "element_count": len(trimmed_elements)},
        )
        try:
            pdf_bytes = self.storage.download(source["storage_path"])
            book = classify(trimmed_elements, pdf_pages=pdf_text_layer(pdf_bytes))
            path = book_work_path(source)
            self.storage.upload(
                path, json.dumps(book.to_dict(), ensure_ascii=False).encode("utf-8"),
                bucket=self.storage.sources_bucket, content_type="application/json",
            )
            self._merge_metadata(source, "structure", {
                "structured_at": utc_now_iso(),
                "stage_version": self.STAGE_VERSION,
                "chapter_count": len(book.chapters),
                "section_count": sum(len(c.sections) for c in book.chapters),
                "body_paragraph_count": book.body_paragraph_count(),
                "dropped_nontext": book.dropped_nontext,
                "book_path": path,
            })
            self._complete(
                stage_run_id,
                output={
                    "chapter_count": len(book.chapters),
                    "section_count": sum(len(c.sections) for c in book.chapters),
                    "chapter_titles": [c.title for c in book.chapters],
                    "dropped_nontext": book.dropped_nontext,
                },
                promoted={"source_ids": [source["id"]], "metadata_namespace": "structure"},
            )
            return stage_run_id, book
        except Exception as exc:
            self._fail(stage_run_id, exc)
            raise


class PdfStructureValidationStageExecutor(_ExecutorBase):
    """Stage: VALIDATE -- cross-check the Book against the source PDF; raises on failure."""

    STAGE_ID = "validate-structure"
    STAGE_VERSION = "1.0"

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
        book: Book,
    ) -> str:
        stage_run_id = self._start(
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            inputs={"source_id": source["id"], "chapter_count": len(book.chapters)},
        )
        try:
            pdf_bytes = self.storage.download(source["storage_path"])
            report = validate_against_pdf(book, pdf_bytes)  # raises StructureValidationError on hard fail
            title_corrections = report.get("title_corrections") or []
            if title_corrections:
                # Create EPUB reloads book.json. Keep the PDF spelling there.
                self.storage.upload(
                    book_work_path(source),
                    json.dumps(book.to_dict(), ensure_ascii=False).encode("utf-8"),
                    bucket=self.storage.sources_bucket,
                    content_type="application/json",
                )
            self._merge_metadata(source, "validate", {
                "validated_at": utc_now_iso(),
                "valid": report["valid"],
                "warnings": report["warnings"],
                "title_corrections": title_corrections,
                "checked": report["checked"],
            })
            self._complete(
                stage_run_id,
                output={"valid": report["valid"], "warnings": report["warnings"],
                        "checked": report["checked"]},
                promoted={"source_ids": [source["id"]], "metadata_namespace": "validate"},
            )
            return stage_run_id
        except Exception as exc:
            self._fail(stage_run_id, exc)
            raise


class CreateEbookStageExecutor(_ExecutorBase):
    """Stage: CREATE EBOOK -- render the Book to EPUB (replaces elevenreader-ebook)."""

    STAGE_ID = "create-ebook"
    STAGE_VERSION = "1.0"
    MODULE = "mathesys"

    def _publication_metadata_from_research(self, source: dict[str, Any]) -> dict[str, Any]:
        research = source.get("source_metadata", {}).get("research") or {}
        if not isinstance(research, dict):
            research = {}
        title = str(research.get("title") or source.get("filename") or "Untitled")
        authors = research.get("authors")
        if isinstance(authors, list) and authors:
            author = str(authors[0])
        elif research.get("issuing_authority"):
            author = str(research.get("issuing_authority"))
        else:
            author = "Foundry"
        identifier = research.get("identifier")
        pub_date = research.get("publication_date_public") or research.get("publication_date_in_document")
        return {
            "title": title,
            "author": author,
            "identifier": str(identifier) if identifier else None,
            "publication_date": str(pub_date) if pub_date else None,
            "language": "en",
        }

    def _prior_publication_snapshot(self, source_id: str) -> dict[str, Any] | None:
        """Reuse title/author from the newest prior electronic_book for this source."""
        for artifact in self.db.list_artifacts_for_source(
            source_id, artifact_type="electronic_book"
        ):
            manifest = artifact.get("manifest") or {}
            if not isinstance(manifest, dict):
                continue
            title = manifest.get("title")
            author = manifest.get("author")
            if not title or not author:
                continue
            identifier = manifest.get("identifier")
            pub_date = manifest.get("publication_date")
            return {
                "title": str(title),
                "author": str(author),
                "identifier": str(identifier) if identifier else None,
                "publication_date": str(pub_date) if pub_date else None,
                "language": "en",
            }
        return None

    def _publication_metadata(self, source: dict[str, Any]) -> dict[str, Any]:
        prior = self._prior_publication_snapshot(source["id"])
        if prior:
            return prior
        return self._publication_metadata_from_research(source)

    def _load_book(self, source: dict[str, Any]) -> Book:
        """Load the structured Book that the structure stage persisted to storage."""
        structure_meta = (source.get("source_metadata") or {}).get("structure") or {}
        book_path = structure_meta.get("book_path") or book_work_path(source)
        if not book_path:
            raise RuntimeError(
                f"No structured book for source {source['id']}; run the structure stage first."
            )
        blob = self.storage.download(book_path, bucket=self.storage.sources_bucket)
        return book_from_dict(json.loads(blob))

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
    ) -> str:
        book = self._load_book(source)
        stage_run_id = self._start(
            production_run_id=production_run_id,
            workspace_id=workspace_id,
            inputs={"source_id": source["id"], "chapter_count": len(book.chapters)},
        )
        try:
            meta = self._publication_metadata(source)
            epub_bytes = build_epub(
                title=meta["title"],
                author=meta["author"],
                identifier=meta["identifier"],
                language=meta["language"],
                publication_date=meta["publication_date"],
                chapters=book_to_epub_chapters(book),
            )

            filename = OUTPUT_FILENAMES["electronic_book"]
            storage_path = downloadable_artifact_path(source, "electronic_book")
            artifact = self.db.create_artifact(
                {
                    "workspace_id": workspace_id,
                    "source_id": source["id"],
                    "production_run_id": production_run_id,
                    "artifact_type": "electronic_book",
                    "format": "epub3",
                    "filename": filename,
                    "storage_path": storage_path,
                    "file_size_bytes": len(epub_bytes),
                    "manifest": {
                        "title": meta["title"],
                        "author": meta["author"],
                        "identifier": meta["identifier"],
                        "publication_date": meta["publication_date"],
                        "chapter_count": len(book.chapters),
                        "section_count": sum(len(c.sections) for c in book.chapters),
                        "chapter_titles": [c.title for c in book.chapters],
                        "structure": source.get("source_metadata", {}).get("structure"),
                    },
                    "origin": {
                        "stage_run_id": stage_run_id,
                        "stage_id": self.STAGE_ID,
                        "stage_version": self.STAGE_VERSION,
                    },
                }
            )
            artifact_id = artifact["id"]
            self.storage.upload(
                storage_path,
                epub_bytes,
                bucket=self.storage.sources_bucket,
                content_type="application/epub+zip",
            )

            self._complete(
                stage_run_id,
                output={"files": [{"artifact_id": artifact_id, "filename": filename,
                                   "storage_path": storage_path}],
                        "chapter_titles": [c.title for c in book.chapters]},
                promoted={"artifact_ids": [artifact_id]},
            )
            return stage_run_id
        except Exception as exc:
            self._fail(stage_run_id, exc)
            raise
