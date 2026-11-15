from datetime import date, time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import require_admin, require_approved_user
from app.dependencies.services import (
    get_calendar_event_repository,
    get_calendar_task_completion_repository,
)
from app.dependencies.workspace import require_workspace
from app.models.auth import CurrentUser
from app.models.calendar import (
    CalendarEventCreate,
    CalendarEventKind,
    CalendarEventResponse,
    CalendarEventUpdate,
    times_in_order,
)
from app.models.workspace import WorkspaceResponse
from app.repositories.calendar_events import CalendarEventRepository, CalendarTaskCompletionRepository

router = APIRouter(prefix="/workspaces", tags=["calendar"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found.")


def _parse_time(value: object) -> time | None:
    if value is None or isinstance(value, time):
        return value
    return time.fromisoformat(str(value))


def _to_response(row: dict[str, Any], completed_at: object | None = None) -> CalendarEventResponse:
    payload = dict(row)
    payload["completed_at"] = completed_at if payload.get("kind") == "deadline" else None
    return CalendarEventResponse.model_validate(payload)


async def _completion_index(
    completions: CalendarTaskCompletionRepository,
    workspace_id: str,
    user_id: str,
) -> dict[str, object]:
    rows = await completions.list_for_user(workspace_id, user_id)
    return {str(row["event_id"]): row["completed_at"] for row in rows}


@router.get("/{workspace_id}/calendar-events", response_model=list[CalendarEventResponse])
async def list_calendar_events(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    events: Annotated[CalendarEventRepository, Depends(get_calendar_event_repository)],
    completions: Annotated[
        CalendarTaskCompletionRepository,
        Depends(get_calendar_task_completion_repository),
    ],
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
    kind: Annotated[CalendarEventKind | None, Query()] = None,
) -> list[CalendarEventResponse]:
    if start and end and end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="End date must be on or after start date.",
        )
    rows = await events.list_for_workspace(workspace.id, start=start, end=end, kind=kind)
    by_event = await _completion_index(completions, workspace.id, user.id)
    return [_to_response(row, by_event.get(str(row["id"]))) for row in rows]


@router.post(
    "/{workspace_id}/calendar-events",
    response_model=CalendarEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_calendar_event(
    payload: CalendarEventCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_admin)],
    events: Annotated[CalendarEventRepository, Depends(get_calendar_event_repository)],
) -> CalendarEventResponse:
    row = await events.create(
        {
            **payload.model_dump(mode="json"),
            "workspace_id": workspace.id,
            "created_by": user.id,
        }
    )
    return _to_response(row)


@router.patch(
    "/{workspace_id}/calendar-events/{event_id}",
    response_model=CalendarEventResponse,
    dependencies=[Depends(require_admin)],
)
async def update_calendar_event(
    event_id: str,
    payload: CalendarEventUpdate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    events: Annotated[CalendarEventRepository, Depends(get_calendar_event_repository)],
) -> CalendarEventResponse:
    existing = await events.get(event_id, workspace.id)
    if not existing:
        raise _not_found()

    updates = payload.model_dump(mode="json", exclude_unset=True)
    for required in ("title", "kind", "event_date"):
        if required in updates and updates[required] is None:
            updates.pop(required)
    if not updates:
        return _to_response(existing)

    start_time = _parse_time(updates.get("start_time", existing.get("start_time")))
    end_time = _parse_time(updates.get("end_time", existing.get("end_time")))
    if not times_in_order(start_time, end_time):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="End time must be at or after start time.",
        )

    row = await events.update(event_id, workspace.id, updates)
    if not row:
        raise _not_found()
    return _to_response(row)


@router.delete(
    "/{workspace_id}/calendar-events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_calendar_event(
    event_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    events: Annotated[CalendarEventRepository, Depends(get_calendar_event_repository)],
) -> None:
    existing = await events.get(event_id, workspace.id)
    if not existing:
        raise _not_found()
    await events.delete(event_id, workspace.id)


def _require_task(existing: dict[str, Any]) -> None:
    if existing.get("kind") != "deadline":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only a task can be checked off.",
        )


@router.put(
    "/{workspace_id}/calendar-events/{event_id}/completion",
    response_model=CalendarEventResponse,
)
async def complete_calendar_task(
    event_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    events: Annotated[CalendarEventRepository, Depends(get_calendar_event_repository)],
    completions: Annotated[
        CalendarTaskCompletionRepository,
        Depends(get_calendar_task_completion_repository),
    ],
) -> CalendarEventResponse:
    existing = await events.get(event_id, workspace.id)
    if not existing:
        raise _not_found()
    _require_task(existing)
    completion = await completions.complete(workspace.id, event_id, user.id)
    return _to_response(existing, completion["completed_at"])


@router.delete(
    "/{workspace_id}/calendar-events/{event_id}/completion",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_calendar_task(
    event_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    events: Annotated[CalendarEventRepository, Depends(get_calendar_event_repository)],
    completions: Annotated[
        CalendarTaskCompletionRepository,
        Depends(get_calendar_task_completion_repository),
    ],
) -> None:
    existing = await events.get(event_id, workspace.id)
    if not existing:
        raise _not_found()
    _require_task(existing)
    await completions.clear(event_id, workspace.id, user.id)
