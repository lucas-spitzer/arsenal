from datetime import date
from typing import Any

from app.services.supabase_rest import SupabaseRestClient

TABLE = "calendar_events"


class CalendarEventRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        start: date | None = None,
        end: date | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = {"workspace_id": f"eq.{workspace_id}"}
        if kind:
            filters["kind"] = f"eq.{kind}"
        if start and end:
            filters["and"] = f"(event_date.gte.{start.isoformat()},event_date.lte.{end.isoformat()})"
        elif start:
            filters["event_date"] = f"gte.{start.isoformat()}"
        elif end:
            filters["event_date"] = f"lte.{end.isoformat()}"
        return await self.db.select_many(
            TABLE,
            filters=filters,
            order="event_date.asc,start_time.asc.nullsfirst,title.asc",
        )

    async def get(self, event_id: str, workspace_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            TABLE,
            filters={"id": f"eq.{event_id}", "workspace_id": f"eq.{workspace_id}"},
        )

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert(TABLE, payload)
        return rows[0]

    async def update(
        self,
        event_id: str,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = await self.db.update(
            TABLE,
            filters={"id": f"eq.{event_id}", "workspace_id": f"eq.{workspace_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def delete(self, event_id: str, workspace_id: str) -> None:
        await self.db.delete(
            TABLE,
            filters={"id": f"eq.{event_id}", "workspace_id": f"eq.{workspace_id}"},
        )


COMPLETIONS = "calendar_task_completions"


class CalendarTaskCompletionRepository:
    """Task checks are private. Every read and write filters on the caller's user id."""

    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            COMPLETIONS,
            filters={
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
        )

    async def get_for_user(
        self,
        event_id: str,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        return await self.db.select_one(
            COMPLETIONS,
            filters={
                "event_id": f"eq.{event_id}",
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
        )

    async def complete(self, workspace_id: str, event_id: str, user_id: str) -> dict[str, Any]:
        existing = await self.get_for_user(event_id, workspace_id, user_id)
        if existing:
            return existing
        rows = await self.db.insert(
            COMPLETIONS,
            {"workspace_id": workspace_id, "event_id": event_id, "user_id": user_id},
        )
        return rows[0]

    async def clear(self, event_id: str, workspace_id: str, user_id: str) -> None:
        await self.db.delete(
            COMPLETIONS,
            filters={
                "event_id": f"eq.{event_id}",
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
        )
