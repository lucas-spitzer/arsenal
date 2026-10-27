from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class RetrievalRepository:
    """Thin wrapper over the pgvector match_* RPCs (see migration 31)."""

    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def match_segments(
        self,
        *,
        embedding: list[float],
        workspace_id: str,
        threshold: float,
        count: int,
        source_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self.db.rpc(
            "match_ndr_segments",
            {
                "query_embedding": embedding,
                "p_workspace_id": workspace_id,
                "match_threshold": threshold,
                "match_count": count,
                "p_source_ids": source_ids,
            },
        )
        return rows or []

    async def match_lesson_chunks(
        self,
        *,
        embedding: list[float],
        workspace_id: str,
        threshold: float,
        count: int,
        lesson_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self.db.rpc(
            "match_lesson_chunks",
            {
                "query_embedding": embedding,
                "p_workspace_id": workspace_id,
                "match_threshold": threshold,
                "match_count": count,
                "p_lesson_ids": lesson_ids,
            },
        )
        return rows or []

    async def match_wiki_entries(
        self,
        *,
        embedding: list[float],
        workspace_id: str,
        threshold: float,
        count: int,
    ) -> list[dict[str, Any]]:
        rows = await self.db.rpc(
            "match_wiki_entries",
            {
                "query_embedding": embedding,
                "p_workspace_id": workspace_id,
                "match_threshold": threshold,
                "match_count": count,
            },
        )
        return rows or []
