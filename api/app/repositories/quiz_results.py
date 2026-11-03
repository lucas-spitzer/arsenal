from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class QuizResultRepository:
    """Quiz results are private. Every read and write filters on the caller's user id."""

    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "quiz_results",
            filters={
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
            order="completed_at.desc",
        )

    async def insert(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("quiz_results", payload)
        return rows[0]
