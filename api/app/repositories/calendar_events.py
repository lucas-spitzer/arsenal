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
    ) -> list[dict[str, Any]]:
        filters = {"workspace_id": f"eq.{workspace_id}"}
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
