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
    clear_calendar_task,
    complete_calendar_task,
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
        self.list_calls: list[tuple[str, date | None, date | None, str | None]] = []
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[str] = []

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        start: date | None = None,
        end: date | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        self.list_calls.append((workspace_id, start, end, kind))
        return [row for row in self.rows if kind is None or row["kind"] == kind]

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


class FakeCompletionRepo:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.listed_for: list[tuple[str, str]] = []
        self.completed: list[tuple[str, str, str]] = []
        self.cleared: list[tuple[str, str, str]] = []

    async def list_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        self.listed_for.append((workspace_id, user_id))
        return [row for row in self.rows if row["workspace_id"] == workspace_id and row["user_id"] == user_id]

    async def complete(self, workspace_id: str, event_id: str, user_id: str) -> dict[str, Any]:
        self.completed.append((workspace_id, event_id, user_id))
        existing = next(
            (
                row
                for row in self.rows
                if row["event_id"] == event_id and row["user_id"] == user_id
            ),
            None,
        )
        if existing:
            return existing
        created = {
            "workspace_id": workspace_id,
            "event_id": event_id,
            "user_id": user_id,
            "completed_at": "2026-11-16T16:00:00+00:00",
        }
        self.rows.append(created)
        return created

    async def clear(self, event_id: str, workspace_id: str, user_id: str) -> None:
        self.cleared.append((event_id, workspace_id, user_id))
        self.rows = [
            row
            for row in self.rows
            if not (row["event_id"] == event_id and row["user_id"] == user_id and row["workspace_id"] == workspace_id)
        ]


def test_list_passes_date_range() -> None:
    repo = FakeCalendarRepo(rows=[_row()])
    completions = FakeCompletionRepo()

    result = asyncio.run(
        list_calendar_events(  # type: ignore[arg-type]
            _workspace(),
            _user(),
            repo,
            completions,
            date(2026, 10, 25),
            date(2026, 10, 31),
        )
    )

    assert repo.list_calls == [("ws-1", date(2026, 10, 25), date(2026, 10, 31), None)]
    assert completions.listed_for == [("ws-1", "user-1")]
    assert [event.title for event in result] == ["TCCC Class"]
    assert result[0].event_date == date(2026, 10, 26)
    assert result[0].completed_at is None


def test_list_marks_only_the_callers_deadlines() -> None:
    deadline = _row(id="due-1", title="Read MCDP-1", kind="deadline", event_date="2026-11-23")
    other = _row(id="class-1")
    repo = FakeCalendarRepo(rows=[deadline, other])
    completions = FakeCompletionRepo(
        rows=[
            {
                "workspace_id": "ws-1",
                "event_id": "due-1",
                "user_id": "user-1",
                "completed_at": "2026-11-16T16:00:00+00:00",
            },
            {
                "workspace_id": "ws-1",
                "event_id": "due-1",
                "user_id": "someone-else",
                "completed_at": "2026-11-15T16:00:00+00:00",
            },
            {
                "workspace_id": "ws-1",
                "event_id": "class-1",
                "user_id": "user-1",
                "completed_at": "2026-11-16T16:00:00+00:00",
            },
        ]
    )

    result = asyncio.run(
        list_calendar_events(_workspace(), _user(), repo, completions)  # type: ignore[arg-type]
    )

    by_id = {event.id: event.completed_at for event in result}
    assert by_id["due-1"] == datetime.fromisoformat("2026-11-16T16:00:00+00:00")
    assert by_id["class-1"] is None


def test_list_rejects_inverted_range() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            list_calendar_events(  # type: ignore[arg-type]
                _workspace(),
                _user(),
                FakeCalendarRepo(),
                FakeCompletionRepo(),
                date(2026, 10, 31),
                date(2026, 10, 25),
            )
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


def test_create_accepts_schedule_kind() -> None:
    payload = CalendarEventCreate(title="Hike to WTBN", kind="schedule", event_date=date(2026, 11, 16))
    assert payload.kind == "schedule"


def test_create_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        CalendarEventCreate(title="Run", kind="pt", event_date=date(2026, 10, 28))  # type: ignore[arg-type]


def test_complete_task_stamps_the_caller() -> None:
    repo = FakeCalendarRepo(rows=[_row(id="due-1", kind="deadline", title="Read MCDP-1")])
    completions = FakeCompletionRepo()

    result = asyncio.run(
        complete_calendar_task("due-1", _workspace(), _user(), repo, completions)  # type: ignore[arg-type]
    )

    assert completions.completed == [("ws-1", "due-1", "user-1")]
    assert result.completed_at == datetime.fromisoformat("2026-11-16T16:00:00+00:00")


def test_complete_again_keeps_the_original_time() -> None:
    repo = FakeCalendarRepo(rows=[_row(id="due-1", kind="deadline")])
    completions = FakeCompletionRepo(
        rows=[
            {
                "workspace_id": "ws-1",
                "event_id": "due-1",
                "user_id": "user-1",
                "completed_at": "2026-11-15T12:00:00+00:00",
            }
        ]
    )

    result = asyncio.run(
        complete_calendar_task("due-1", _workspace(), _user(), repo, completions)  # type: ignore[arg-type]
    )

    assert completions.completed == [("ws-1", "due-1", "user-1")]
    assert result.completed_at == datetime.fromisoformat("2026-11-15T12:00:00+00:00")
    assert len(completions.rows) == 1


def test_complete_rejects_a_class() -> None:
    repo = FakeCalendarRepo(rows=[_row()])
    completions = FakeCompletionRepo()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            complete_calendar_task("ev-1", _workspace(), _user(), repo, completions)  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 422
    assert completions.completed == []


def test_complete_missing_event_404() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            complete_calendar_task(  # type: ignore[arg-type]
                "missing",
                _workspace(),
                _user(),
                FakeCalendarRepo(),
                FakeCompletionRepo(),
            )
        )
    assert exc.value.status_code == 404


def test_clear_task_removes_the_callers_row() -> None:
    repo = FakeCalendarRepo(rows=[_row(id="due-1", kind="deadline")])
    completions = FakeCompletionRepo(
        rows=[
            {
                "workspace_id": "ws-1",
                "event_id": "due-1",
                "user_id": "user-1",
                "completed_at": "2026-11-16T16:00:00+00:00",
            }
        ]
    )

    asyncio.run(
        clear_calendar_task("due-1", _workspace(), _user(), repo, completions)  # type: ignore[arg-type]
    )

    assert completions.cleared == [("due-1", "ws-1", "user-1")]
    assert completions.rows == []


def test_clear_rejects_a_class() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            clear_calendar_task("ev-1", _workspace(), _user(), FakeCalendarRepo(rows=[_row()]), FakeCompletionRepo())  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 422


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


def test_repository_filters_by_kind() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            self.calls.append({"table": table, **kwargs})
            return []

    db = FakeDb()
    repo = CalendarEventRepository(db)  # type: ignore[arg-type]

    asyncio.run(repo.list_for_workspace("ws-1", kind="deadline"))

    assert db.calls[0]["filters"]["kind"] == "eq.deadline"
