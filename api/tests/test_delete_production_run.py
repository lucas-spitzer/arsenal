from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from app.models.auth import CurrentUser
from app.models.workspace import WorkspaceResponse
from app.routers.production_runs import delete_production_run
from app.services.queue import cancel_queued_jobs_for_run


def _workspace() -> WorkspaceResponse:
    now = datetime.now(UTC)
    return WorkspaceResponse(
        id="ws-1",
        owner_id="owner-1",
        name="Test",
        slug="test",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def _user() -> CurrentUser:
    return CurrentUser(id="owner-1", email="owner@example.com", role="approved")


class FakeProductionRunRepository:
    def __init__(self, row: dict[str, Any] | None, storage_rows: list[dict[str, Any]] | None = None) -> None:
        self.row = row
        self.storage_rows = storage_rows or []
        self.purged: list[str] = []

    async def get_for_owner(self, production_run_id: str, owner_id: str) -> dict[str, Any] | None:
        if not self.row:
            return None
        if self.row["id"] != production_run_id or self.row["owner_id"] != owner_id:
            return None
        return self.row

    async def purge(self, production_run_id: str) -> list[dict[str, Any]]:
        self.purged.append(production_run_id)
        return self.storage_rows


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, list[str]]] = []

    async def delete_paths(self, *, bucket: str, paths: list[str]) -> None:
        self.deleted.append((bucket, paths))


class FakeJob:
    def __init__(self, args: tuple[Any, ...]) -> None:
        self.args = args
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeQueue:
    def __init__(self, jobs: list[FakeJob]) -> None:
        self.jobs = jobs


def _run_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "run-1",
        "workspace_id": "ws-1",
        "owner_id": "owner-1",
        "status": "completed",
    }
    row.update(overrides)
    return row


def test_delete_missing_run_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    cancelled: list[str] = []
    monkeypatch.setattr(
        "app.services.production_runs.cancel_queued_jobs_for_run",
        lambda _settings, run_id: cancelled.append(run_id),
    )
    repo = FakeProductionRunRepository(None)
    storage = FakeStorage()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            delete_production_run(
                "run-1",
                _workspace(),
                _user(),
                object(),  # type: ignore[arg-type]
                repo,  # type: ignore[arg-type]
                storage,  # type: ignore[arg-type]
            ),
        )

    assert exc.value.status_code == 404
    assert repo.purged == []
    assert storage.deleted == []
    assert cancelled == []


def test_delete_run_from_another_workspace_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.production_runs.cancel_queued_jobs_for_run",
        lambda _settings, _run_id: None,
    )
    repo = FakeProductionRunRepository(_run_row(workspace_id="ws-other"))
    storage = FakeStorage()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            delete_production_run(
                "run-1",
                _workspace(),
                _user(),
                object(),  # type: ignore[arg-type]
                repo,  # type: ignore[arg-type]
                storage,  # type: ignore[arg-type]
            ),
        )

    assert exc.value.status_code == 404
    assert repo.purged == []


def test_delete_purges_run_storage_and_cancels_queued_job(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(
        "app.services.production_runs.cancel_queued_jobs_for_run",
        lambda _settings, run_id: order.append(f"cancel:{run_id}"),
    )
    repo = FakeProductionRunRepository(
        _run_row(),
        storage_rows=[
            {"bucket": "sources", "name": "ocs-prep/book.pdf"},
            {"bucket": "sources", "name": "pending"},
            {"bucket": "sources", "name": ""},
            {"bucket": "", "name": "ignored"},
        ],
    )
    original_purge = repo.purge

    async def purge(production_run_id: str) -> list[dict[str, Any]]:
        order.append(f"purge:{production_run_id}")
        return await original_purge(production_run_id)

    repo.purge = purge  # type: ignore[method-assign]
    storage = FakeStorage()

    asyncio.run(
        delete_production_run(
            "run-1",
            _workspace(),
            _user(),
            object(),  # type: ignore[arg-type]
            repo,  # type: ignore[arg-type]
            storage,  # type: ignore[arg-type]
        ),
    )

    assert order == ["cancel:run-1", "purge:run-1"]
    assert repo.purged == ["run-1"]
    assert storage.deleted == [("sources", ["ocs-prep/book.pdf"])]


def test_cancel_queued_jobs_only_for_this_run(monkeypatch: pytest.MonkeyPatch) -> None:
    match = FakeJob(("run-1",))
    other = FakeJob(("run-2",))
    empty = FakeJob(())
    monkeypatch.setattr(
        "app.services.queue.get_task_queue",
        lambda _settings: FakeQueue([match, other, empty]),
    )

    cancel_queued_jobs_for_run(object(), "run-1")  # type: ignore[arg-type]

    assert match.cancelled is True
    assert other.cancelled is False
    assert empty.cancelled is False
