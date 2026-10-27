from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.auth import CurrentUser
from app.models.calendar import CalendarEventCreate, CalendarEventUpdate
from app.models.workspace import WorkspaceResponse
from app.repositories.calendar_events import CalendarEventRepository
from app.routers.calendar import (
    create_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    update_calendar_event,
)


def _workspace() -> WorkspaceResponse:
    now = datetime.now(UTC)
    return WorkspaceResponse(
        id="ws-1",
        owner_id="owner-1",
        name="The Basic School",
        slug="the-basic-school",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def _user() -> CurrentUser:
    return CurrentUser(id="user-1", email="admin@example.com", role="admin")


def _row(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    row: dict[str, Any] = {
        "id": "ev-1",
        "workspace_id": "ws-1",
        "title": "TCCC Class",
        "kind": "class",
        "event_date": "2026-10-26",
        "start_time": None,
        "end_time": None,
        "location": "CR-3",
        "notes": None,
        "created_by": "user-1",
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


class FakeCalendarRepo:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.list_calls: list[tuple[str, date | None, date | None]] = []
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[str] = []

    async def list_for_workspace(
        self, workspace_id: str, *, start: date | None = None, end: date | None = None
    ) -> list[dict[str, Any]]:
        self.list_calls.append((workspace_id, start, end))
        return self.rows

    async def get(self, event_id: str, workspace_id: str) -> dict[str, Any] | None:
        return next((r for r in self.rows if r["id"] == event_id and r["workspace_id"] == workspace_id), None)

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(payload)
        return _row(**payload)

    async def update(self, event_id: str, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.updated.append((event_id, payload))
        existing = await self.get(event_id, workspace_id)
        return {**existing, **payload} if existing else None

    async def delete(self, event_id: str, workspace_id: str) -> None:
        self.deleted.append(event_id)


def test_list_passes_date_range() -> None:
    repo = FakeCalendarRepo(rows=[_row()])

    result = asyncio.run(
        list_calendar_events(_workspace(), repo, date(2026, 10, 25), date(2026, 10, 31))  # type: ignore[arg-type]
    )

    assert repo.list_calls == [("ws-1", date(2026, 10, 25), date(2026, 10, 31))]
    assert [event.title for event in result] == ["TCCC Class"]
    assert result[0].event_date == date(2026, 10, 26)


def test_list_rejects_inverted_range() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            list_calendar_events(_workspace(), FakeCalendarRepo(), date(2026, 10, 31), date(2026, 10, 25))  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 422


def test_create_scopes_to_workspace_and_trims() -> None:
    repo = FakeCalendarRepo()
    payload = CalendarEventCreate(
        title="  TCCC Prac App ",
        kind="prac_app",
        event_date=date(2026, 10, 27),
        location="  ",
    )

    result = asyncio.run(create_calendar_event(payload, _workspace(), _user(), repo))  # type: ignore[arg-type]

    created = repo.created[0]
    assert created["workspace_id"] == "ws-1"
    assert created["created_by"] == "user-1"
    assert created["title"] == "TCCC Prac App"
    assert created["event_date"] == "2026-10-27"
    assert created["location"] is None
    assert result.kind == "prac_app"


def test_create_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        CalendarEventCreate(
            title="TCCC Evaluation",
            event_date=date(2026, 10, 28),
            start_time=time(10, 0),
            end_time=time(9, 0),
        )


def test_create_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        CalendarEventCreate(title="Run", kind="pt", event_date=date(2026, 10, 28))  # type: ignore[arg-type]


def test_update_missing_event_404() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_calendar_event("missing", CalendarEventUpdate(title="X"), _workspace(), FakeCalendarRepo())  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404


def test_update_checks_times_against_stored_row() -> None:
    repo = FakeCalendarRepo(rows=[_row(start_time="13:00:00")])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_calendar_event("ev-1", CalendarEventUpdate(end_time=time(12, 0)), _workspace(), repo)  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 422
    assert repo.updated == []


def test_update_applies_partial_changes() -> None:
    repo = FakeCalendarRepo(rows=[_row()])

    result = asyncio.run(
        update_calendar_event(
            "ev-1",
            CalendarEventUpdate(location="CR-1", start_time=time(8, 0)),
            _workspace(),
            repo,
        )  # type: ignore[arg-type]
    )

    assert repo.updated == [("ev-1", {"location": "CR-1", "start_time": "08:00:00"})]
    assert result.location == "CR-1"
    assert result.start_time == time(8, 0)


def test_delete_missing_event_404() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_calendar_event("missing", _workspace(), FakeCalendarRepo()))  # type: ignore[arg-type]
    assert exc.value.status_code == 404


def test_delete_removes_event() -> None:
    repo = FakeCalendarRepo(rows=[_row()])

    asyncio.run(delete_calendar_event("ev-1", _workspace(), repo))  # type: ignore[arg-type]

    assert repo.deleted == ["ev-1"]


def test_repository_builds_range_filter() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            self.calls.append({"table": table, **kwargs})
            return []

    db = FakeDb()
    repo = CalendarEventRepository(db)  # type: ignore[arg-type]

    asyncio.run(repo.list_for_workspace("ws-1", start=date(2026, 10, 25), end=date(2026, 10, 31)))

    call = db.calls[0]
    assert call["table"] == "calendar_events"
    assert call["filters"] == {
        "workspace_id": "eq.ws-1",
        "and": "(event_date.gte.2026-10-25,event_date.lte.2026-10-31)",
    }
    assert call["order"].startswith("event_date.asc")
