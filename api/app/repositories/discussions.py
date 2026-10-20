from datetime import UTC, datetime
from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class DiscussionRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_threads(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "discussion_threads",
            filters={
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
            order="updated_at.desc",
        )

    async def get_thread(
        self,
        thread_id: str,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        return await self.db.select_one(
            "discussion_threads",
            filters={
                "id": f"eq.{thread_id}",
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
        )

    async def create_thread(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("discussion_threads", payload)
        return rows[0]

    async def update_thread(
        self,
        thread_id: str,
        workspace_id: str,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = await self.db.update(
            "discussion_threads",
            filters={
                "id": f"eq.{thread_id}",
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
            payload=payload,
        )
        return rows[0] if rows else None

    async def touch_thread(self, thread_id: str, workspace_id: str, user_id: str) -> None:
        """Bump updated_at so the thread sorts to the top of recent activity."""
        await self.update_thread(
            thread_id,
            workspace_id,
            user_id,
            {"updated_at": datetime.now(UTC).isoformat()},
        )

    async def delete_thread(self, thread_id: str, workspace_id: str, user_id: str) -> None:
        await self.db.delete(
            "discussion_threads",
            filters={
                "id": f"eq.{thread_id}",
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
        )

    async def list_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "discussion_messages",
            filters={"thread_id": f"eq.{thread_id}"},
            order="created_at.asc",
        )

    async def append_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("discussion_messages", payload)
        return rows[0]
