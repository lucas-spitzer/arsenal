"""Tests for create-ebook publication freeze and partial structure reload."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.intellex.structuring.models import Book, Chapter, Element, Paragraph
from app.worker.pipeline_runner import PipelineContext, PipelineRunner
from app.worker.structuring_executors import CreateEbookStageExecutor


def _minimal_book() -> Book:
    book = Book()
    chapter = Chapter(title="Chapter 1 Test", page=1)
    chapter.intro = [Paragraph(md="Body text.", page=1)]
    book.chapters.append(chapter)
    return book


def test_create_ebook_prefers_prior_manifest_publication_metadata() -> None:
    db = MagicMock()
    storage = MagicMock()
    db.create_stage_run.return_value = {"id": "sr-1"}
    db.create_artifact.return_value = {"id": "art-new"}
    db.list_artifacts_for_source.return_value = [
        {
            "id": "art-old",
            "manifest": {
                "title": "Warfighting",
                "author": "United States Marine Corps",
                "identifier": "MCDP 1",
                "publication_date": "1997-06-20",
            },
        }
    ]
    storage.download.return_value = json.dumps(_minimal_book().to_dict()).encode("utf-8")

    source = {
        "id": "src-1",
        "slug": "src-1",
        "workspace_slug": "ocs-prep",
        "filename": "other.pdf",
        "storage_path": "ocs-prep/src-1/file.pdf",
        "source_metadata": {
            "structure": {"book_path": "ocs-prep/src-1/work/book.json"},
            "research": {
                "title": "Should Not Win",
                "authors": ["Someone Else"],
                "researched_at": "2026-07-18T00:00:00+00:00",
            },
        },
    }

    executor = CreateEbookStageExecutor(db=db, storage=storage)
    stage_run_id = executor.run_for_source(
        production_run_id="pr-1",
        workspace_id="ws-1",
        source=source,
    )

    assert stage_run_id == "sr-1"
    created = db.create_artifact.call_args.args[0]
    assert created["manifest"]["title"] == "Warfighting"
    assert created["manifest"]["author"] == "United States Marine Corps"
    assert created["manifest"]["identifier"] == "MCDP 1"
    assert created["filename"] == "Warfighting.epub"
    assert storage.upload.call_args.args[0] == "ocs-prep/src-1/book.epub"


def test_create_ebook_falls_back_to_research_when_no_prior_snapshot() -> None:
    db = MagicMock()
    storage = MagicMock()
    db.create_stage_run.return_value = {"id": "sr-1"}
    db.create_artifact.return_value = {"id": "art-new"}
    db.list_artifacts_for_source.return_value = []
    storage.download.return_value = json.dumps(_minimal_book().to_dict()).encode("utf-8")

    source = {
        "id": "src-1",
        "slug": "src-1",
        "workspace_slug": "ocs-prep",
        "filename": "file.pdf",
        "storage_path": "ocs-prep/src-1/file.pdf",
        "source_metadata": {
            "structure": {"book_path": "ocs-prep/src-1/work/book.json"},
            "research": {
                "title": "Warfighting",
                "issuing_authority": "US Marine Corps",
                "researched_at": "2026-07-18T00:00:00+00:00",
            },
        },
    }

    executor = CreateEbookStageExecutor(db=db, storage=storage)
    executor.run_for_source(
        production_run_id="pr-1",
        workspace_id="ws-1",
        source=source,
    )

    created = db.create_artifact.call_args.args[0]
    assert created["manifest"]["title"] == "Warfighting"
    assert created["manifest"]["author"] == "US Marine Corps"
    assert created["filename"] == "Warfighting.epub"
    assert created["storage_path"] == "ocs-prep/src-1/book.epub"


def test_normalize_reloads_structured_pages_when_parse_was_reused() -> None:
    db = MagicMock()
    storage = MagicMock()
    normalize = MagicMock()
    normalize.run_for_source.return_value = ("sr-norm", [])

    pages = [{"page_number": 1, "items": []}]
    storage.download.return_value = json.dumps({"pages": pages}).encode("utf-8")

    source = {
        "id": "src-1",
        "storage_path": "workspaces/ws/sources/src-1/file.pdf",
        "source_metadata": {
            "parse": {
                "parsed_at": "2026-07-18T00:00:00+00:00",
                "structured_pages_path": "workspaces/ws/sources/src-1/parse/structured.json",
            },
        },
    }
    context = PipelineContext(
        production_run_id="pr-1",
        workspace_id="ws-1",
        sources=[source],
    )

    runner = PipelineRunner(db=db, storage=storage, normalize=normalize)
    runner.run_normalize_step(context, [{"step": "normalize-document", "status": "pending"}])

    storage.download.assert_called_once()
    normalize.run_for_source.assert_called_once()
    assert normalize.run_for_source.call_args.kwargs["structured_pages"] == pages
    assert context.structured_pages["src-1"] == pages


def test_source_research_skips_when_research_already_complete() -> None:
    db = MagicMock()
    storage = MagicMock()
    source_research = MagicMock()

    source = {
        "id": "src-1",
        "storage_path": "workspaces/ws/sources/src-1/file.pdf",
        "source_metadata": {
            "research": {"researched_at": "2026-07-18T00:00:00+00:00", "title": "Warfighting"},
        },
    }
    context = PipelineContext(
        production_run_id="pr-1",
        workspace_id="ws-1",
        sources=[source],
    )

    runner = PipelineRunner(db=db, storage=storage, source_research=source_research)
    pipeline = runner.run_source_research_step(
        context, [{"step": "source-research", "status": "pending"}]
    )

    source_research.run_for_source.assert_not_called()
    step = next(s for s in pipeline if s["step"] == "source-research")
    assert "1 reused" in step["detail"]


def test_source_research_rebuilds_document_when_parse_was_reused() -> None:
    db = MagicMock()
    storage = MagicMock()
    source_research = MagicMock()
    source_research.run_for_source.return_value = "sr-research"

    source = {
        "id": "src-1",
        "storage_path": "workspaces/ws/sources/src-1/file.pdf",
        "source_metadata": {
            "parse": {
                "parsed_at": "2026-07-18T00:00:00+00:00",
                "page_count": 4,
                "parser": "llamaparse",
                "llamaparse_job_id": "job-1",
            },
        },
    }
    context = PipelineContext(
        production_run_id="pr-1",
        workspace_id="ws-1",
        sources=[source],
    )
    context.normalized_elements["src-1"] = [
        Element(
            index=0,
            page=1,
            type="heading",
            level=1,
            text="MCDP 1-3 Tactics",
            md="# MCDP 1-3 Tactics",
        ),
        Element(
            index=1,
            page=2,
            type="text",
            level=None,
            text="This publication describes tactics.",
            md="This publication describes tactics.",
        ),
        Element(
            index=2,
            page=2,
            type="image",
            level=None,
            text="figure.png",
            md="figure.png",
        ),
    ]

    runner = PipelineRunner(db=db, storage=storage, source_research=source_research)
    runner.run_source_research_step(
        context,
        [{"step": "source-research", "status": "pending"}],
    )

    document = source_research.run_for_source.call_args.kwargs["parsed_document"]
    assert document.page_count == 4
    assert document.parser == "llamaparse"
    assert document.job_id == "job-1"
    assert [(line.kind, line.text) for line in document.lines] == [
        ("heading", "MCDP 1-3 Tactics"),
        ("paragraph", "This publication describes tactics."),
    ]
    assert context.parsed_documents["src-1"] is document
