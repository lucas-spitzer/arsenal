from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class StudyMaterialRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("study_materials", payload)
        return rows[0]

    async def get_for_owner(self, material_id: str, owner_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "study_materials",
            filters={"id": f"eq.{material_id}", "owner_id": f"eq.{owner_id}"},
        )

    async def list_for_workspace(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "study_materials",
            filters={"workspace_id": f"eq.{workspace_id}", "owner_id": f"eq.{owner_id}"},
            order="updated_at.desc",
        )

    async def list_slugs_for_workspace(self, workspace_id: str) -> set[str]:
        rows = await self.db.select_many(
            "study_materials",
            filters={"workspace_id": f"eq.{workspace_id}"},
            columns="slug",
        )
        return {str(row["slug"]) for row in rows}

    async def update(self, material_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.db.update(
            "study_materials",
            filters={"id": f"eq.{material_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def delete(self, material_id: str) -> None:
        await self.db.delete("study_materials", filters={"id": f"eq.{material_id}"})

    async def list_components(self, material_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "study_material_components",
            filters={"study_material_id": f"eq.{material_id}"},
            order="position.asc,created_at.asc",
        )

    async def list_components_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "study_material_components",
            filters={"workspace_id": f"eq.{workspace_id}"},
            columns="id,study_material_id",
        )

    async def get_component(self, material_id: str, component_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "study_material_components",
            filters={"id": f"eq.{component_id}", "study_material_id": f"eq.{material_id}"},
        )

    async def create_component(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("study_material_components", payload)
        return rows[0]

    async def update_component(self, component_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.db.update(
            "study_material_components",
            filters={"id": f"eq.{component_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def delete_component(self, component_id: str) -> None:
        await self.db.delete("study_material_components", filters={"id": f"eq.{component_id}"})

    async def list_versions(self, material_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "study_material_component_versions",
            filters={"study_material_id": f"eq.{material_id}"},
            order="version.asc",
        )
