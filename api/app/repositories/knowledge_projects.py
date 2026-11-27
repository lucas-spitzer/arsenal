from typing import Any

from app.services.supabase_rest import SupabaseRestClient

# PostgREST returns at most this many rows per request.
_REST_PAGE = 1000
_WRITE_CHUNK = 200


class KnowledgeProjectRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("knowledge_projects", payload)
        return rows[0]

    async def get_for_owner(self, project_id: str, owner_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "knowledge_projects",
            filters={"id": f"eq.{project_id}", "owner_id": f"eq.{owner_id}"},
        )

    async def list_for_workspace(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "knowledge_projects",
            filters={"workspace_id": f"eq.{workspace_id}", "owner_id": f"eq.{owner_id}"},
            order="updated_at.desc",
        )

    async def get_in_workspace(self, project_id: str, workspace_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "knowledge_projects",
            filters={"id": f"eq.{project_id}", "workspace_id": f"eq.{workspace_id}"},
            columns="id,source_id,title",
        )

    async def list_titles(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "knowledge_projects",
            filters={"workspace_id": f"eq.{workspace_id}"},
            columns="id,source_id,title",
            order="updated_at.desc",
        )

    async def update(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.db.update(
            "knowledge_projects",
            filters={"id": f"eq.{project_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def delete(self, project_id: str) -> None:
        await self.db.delete("knowledge_projects", filters={"id": f"eq.{project_id}"})

    async def insert_plans(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self._insert_chunks("knowledge_item_plans", rows)

    async def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self._insert_chunks(table, rows)

    async def _insert_chunks(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        saved: list[dict[str, Any]] = []
        for start in range(0, len(rows), _WRITE_CHUNK):
            saved.extend(await self.db.insert(table, rows[start : start + _WRITE_CHUNK]))
        return saved

    async def delete_rows(self, table: str, row_ids: list[str]) -> None:
        if not row_ids:
            return
        await self.db.delete(table, filters={"id": f"in.({','.join(row_ids)})"})

    async def update_row(self, table: str, row_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.db.update(table, filters={"id": f"eq.{row_id}"}, payload=payload)
        return rows[0] if rows else None

    async def list_plans(self, project_id: str) -> list[dict[str, Any]]:
        return await self._every(
            "knowledge_item_plans",
            filters={"knowledge_project_id": f"eq.{project_id}"},
            order="created_at.asc",
        )

    async def get_plan(self, project_id: str, plan_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "knowledge_item_plans",
            filters={"id": f"eq.{plan_id}", "knowledge_project_id": f"eq.{project_id}"},
        )

    async def update_plan(self, plan_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.db.update(
            "knowledge_item_plans",
            filters={"id": f"eq.{plan_id}"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def list_assessments(self, table: str, project_id: str) -> list[dict[str, Any]]:
        return await self._every(
            table,
            filters={"knowledge_project_id": f"eq.{project_id}"},
            order="created_at.asc",
        )

    async def _every(
        self,
        table: str,
        *,
        filters: dict[str, str],
        order: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self.db.select_many(
                table,
                filters=filters,
                order=order,
                limit=_REST_PAGE,
                offset=offset,
            )
            rows.extend(page)
            if len(page) < _REST_PAGE:
                return rows
            offset += len(page)
