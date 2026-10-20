from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class WorkspaceRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def create(
        self,
        *,
        owner_id: str,
        name: str,
        slug: str,
        description: str | None,
    ) -> dict[str, Any]:
        rows = await self.db.insert(
            "workspaces",
            {
                "owner_id": owner_id,
                "name": name,
                "slug": slug,
                "description": description,
            },
        )
        return rows[0]

    async def list_slugs(self) -> set[str]:
        rows = await self.db.select_many("workspaces", columns="slug")
        return {str(row["slug"]) for row in rows if row.get("slug")}

    async def get(self, workspace_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "workspaces",
            filters={"id": f"eq.{workspace_id}"},
        )

    async def list_all(self) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "workspaces",
            order="created_at.desc",
        )

    async def list_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "workspaces",
            filters={"owner_id": f"eq.{owner_id}"},
            order="created_at.desc",
        )

    async def get_for_owner(self, workspace_id: str, owner_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "workspaces",
            filters={
                "id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
            },
        )

    async def update(
        self,
        workspace_id: str,
        owner_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = await self.db.update(
            "workspaces",
            filters={
                "id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
            },
            payload=payload,
        )
        return rows[0] if rows else None

    async def delete(self, workspace_id: str, owner_id: str) -> None:
        await self.db.delete(
            "workspaces",
            filters={
                "id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
            },
        )
