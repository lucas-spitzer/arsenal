from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class NarrationSegmentRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_for_source(
        self,
        source_id: str,
        workspace_id: str,
        owner_id: str,
        *,
        model_id: str | None = None,
        voice_id: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        await self._assert_source_access(source_id, workspace_id, owner_id)

        if not model_id or not voice_id:
            latest = await self.db.select_many(
                "narration_segments",
                filters={
                    "source_id": f"eq.{source_id}",
                    "workspace_id": f"eq.{workspace_id}",
                },
                columns="model_id,voice_id",
                order="updated_at.desc,id.desc",
                limit=1,
            )
            if not latest:
                return []
            model_id = str(latest[0]["model_id"])
            voice_id = str(latest[0]["voice_id"])

        return await self.db.select_many(
            "narration_segments",
            filters={
                "source_id": f"eq.{source_id}",
                "workspace_id": f"eq.{workspace_id}",
                "model_id": f"eq.{model_id}",
                "voice_id": f"eq.{voice_id}",
            },
            order="created_at.asc,id.asc",
            limit=limit,
            offset=offset,
        )

    async def get_by_id(
        self,
        source_id: str,
        narration_id: str,
        workspace_id: str,
        owner_id: str,
    ) -> dict[str, Any] | None:
        await self._assert_source_access(source_id, workspace_id, owner_id)

        return await self.db.select_one(
            "narration_segments",
            filters={
                "id": f"eq.{narration_id}",
                "source_id": f"eq.{source_id}",
                "workspace_id": f"eq.{workspace_id}",
            },
        )

    async def _assert_source_access(
        self,
        source_id: str,
        workspace_id: str,
        owner_id: str,
    ) -> None:
        source = await self.db.select_one(
            "sources",
            filters={
                "id": f"eq.{source_id}",
                "workspace_id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
            },
            columns="id",
        )

        if not source:
            raise LookupError("Source not found.")
