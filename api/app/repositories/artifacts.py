from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class ArtifactRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        artifact_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters: dict[str, str] = {"workspace_id": f"eq.{workspace_id}"}

        if artifact_type:
            filters["artifact_type"] = f"eq.{artifact_type}"

        return await self.db.select_many(
            "artifacts",
            filters=filters,
            order="created_at.desc",
            limit=limit,
            offset=offset,
        )

    async def get_for_workspace(
        self,
        artifact_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        return await self.db.select_one(
            "artifacts",
            filters={
                "id": f"eq.{artifact_id}",
                "workspace_id": f"eq.{workspace_id}",
            },
        )

    async def get_for_owner(
        self,
        artifact_id: str,
        owner_id: str,
    ) -> dict[str, Any] | None:
        artifact = await self.db.select_one(
            "artifacts",
            filters={"id": f"eq.{artifact_id}"},
        )

        if not artifact:
            return None

        workspace = await self.db.select_one(
            "workspaces",
            filters={
                "id": f"eq.{artifact['workspace_id']}",
                "owner_id": f"eq.{owner_id}",
            },
            columns="id",
        )

        if not workspace:
            return None

        return artifact

    async def list_narration_for_source(
        self,
        source_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "artifacts",
            filters={
                "source_id": f"eq.{source_id}",
                "workspace_id": f"eq.{workspace_id}",
                "artifact_type": "eq.narration_audio",
            },
        )

    async def delete(self, artifact_id: str) -> None:
        await self.db.delete("artifacts", filters={"id": f"eq.{artifact_id}"})
