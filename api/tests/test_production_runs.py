from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services.production_runs import (
    ProductionRunValidationError,
    create_and_enqueue_production_run,
)


class FakeProductionRunRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "id": f"run-{self._next_id}"}
        self._next_id += 1
        self.rows[row["id"]] = row
        return row

    async def update(self, production_run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.rows[production_run_id] = {**self.rows[production_run_id], **payload}
        return self.rows[production_run_id]


class FakeBatchRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def insert(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "id": f"batch-{len(self.rows) + 1}"}
        self.rows.append(row)
        return row


def _source(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "src-1",
        "filename": "notes.md",
        "mime_type": "text/markdown",
        "storage_path": "ocs-prep/notes.md",
        "file_size_bytes": 42,
    }
    row.update(overrides)
    return row


def test_wiki_knowledge_run_creates_batch_from_source(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = FakeProductionRunRepository()
    batches = FakeBatchRepository()
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.services.production_runs.enqueue_production_run",
        lambda _settings, run_id: enqueued.append(run_id) or "job-1",
    )

    row = asyncio.run(
        create_and_enqueue_production_run(
            workspace_id="ws-1",
            owner_id="user-1",
            source_ids=["src-1"],
            target_artifacts=["wiki_knowledge"],
            settings=object(),  # type: ignore[arg-type]
            production_runs=runs,  # type: ignore[arg-type]
            sources=[_source()],
            batches=batches,  # type: ignore[arg-type]
        ),
    )

    assert row["id"] == "run-1"
    assert enqueued == ["run-1"]
    assert len(batches.rows) == 1
    batch = batches.rows[0]
    assert batch["production_run_id"] == "run-1"
    assert batch["source_id"] == "src-1"
    assert batch["status"] == "transcribing"
    assert batch["raw_notes"] == ""
    assert batch["attachments"][0]["storage_path"] == "ocs-prep/notes.md"
    assert batch["attachments"][0]["filename"] == "notes.md"
    steps = [step["step"] for step in row["pipeline"]]
    assert "transcribe-wiki-notes" in steps
    assert "structure-wiki-notes" in steps


def test_wiki_knowledge_run_creates_one_batch_per_source(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = FakeProductionRunRepository()
    batches = FakeBatchRepository()
    monkeypatch.setattr(
        "app.services.production_runs.enqueue_production_run",
        lambda *_args, **_kwargs: "job-1",
    )

    asyncio.run(
        create_and_enqueue_production_run(
            workspace_id="ws-1",
            owner_id="user-1",
            source_ids=["src-1", "src-2"],
            target_artifacts=["wiki_knowledge"],
            settings=object(),  # type: ignore[arg-type]
            production_runs=runs,  # type: ignore[arg-type]
            sources=[
                _source(id="src-1", filename="a.md", storage_path="a.md"),
                _source(id="src-2", filename="b.pdf", storage_path="b.pdf", mime_type="application/pdf"),
            ],
            batches=batches,  # type: ignore[arg-type]
        ),
    )

    assert [row["source_id"] for row in batches.rows] == ["src-1", "src-2"]
    assert batches.rows[1]["attachments"][0]["filename"] == "b.pdf"


def test_non_wiki_run_does_not_create_ingest_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = FakeProductionRunRepository()
    batches = FakeBatchRepository()
    monkeypatch.setattr(
        "app.services.production_runs.enqueue_production_run",
        lambda *_args, **_kwargs: "job-1",
    )

    asyncio.run(
        create_and_enqueue_production_run(
            workspace_id="ws-1",
            owner_id="user-1",
            source_ids=["src-1"],
            target_artifacts=["study_sheet"],
            settings=object(),  # type: ignore[arg-type]
            production_runs=runs,  # type: ignore[arg-type]
            sources=[_source()],
            batches=batches,  # type: ignore[arg-type]
        ),
    )

    assert batches.rows == []


def test_wiki_knowledge_run_rejects_source_without_storage_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = FakeProductionRunRepository()
    batches = FakeBatchRepository()
    monkeypatch.setattr(
        "app.services.production_runs.enqueue_production_run",
        lambda *_args, **_kwargs: "job-1",
    )

    with pytest.raises(ProductionRunValidationError, match="storage path"):
        asyncio.run(
            create_and_enqueue_production_run(
                workspace_id="ws-1",
                owner_id="user-1",
                source_ids=["src-1"],
                target_artifacts=["wiki_knowledge"],
                settings=object(),  # type: ignore[arg-type]
                production_runs=runs,  # type: ignore[arg-type]
                sources=[_source(storage_path="")],
                batches=batches,  # type: ignore[arg-type]
            ),
        )

    assert runs.rows["run-1"]["status"] == "failed"
    assert batches.rows == []
    assert "transcribe-wiki-notes" in [
        step["step"] for step in runs.rows["run-1"]["pipeline"]
    ]
