from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class ProductionRunRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("production_runs", payload)
        return rows[0]

    async def get(self, production_run_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "production_runs",
            filters={"id": f"eq.{production_run_id}"},
        )

    async def get_for_owner(
        self,
        production_run_id: str,
        owner_id: str,
    ) -> dict[str, Any] | None:
        return await self.db.select_one(
            "production_runs",
            filters={
                "id": f"eq.{production_run_id}",
                "owner_id": f"eq.{owner_id}",
            },
        )

    async def list_for_workspace(
        self,
        workspace_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "production_runs",
            filters={
                "workspace_id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
            },
            order="created_at.desc",
        )

    async def update(
        self,
        production_run_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = await self.db.update(
            "production_runs",
            filters={"id": f"eq.{production_run_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def purge(self, production_run_id: str) -> list[dict[str, Any]]:
        rows = await self.db.rpc(
            "purge_production_run",
            {"p_run_id": production_run_id},
        )
        if not rows:
            return []
        if isinstance(rows, dict):
            return [rows]
        return [row for row in rows if isinstance(row, dict)]
