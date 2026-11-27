from typing import Any

from app.services.supabase_rest import SupabaseRestClient

# PostgREST returns at most this many rows per request.
_REST_PAGE = 1000
# One insert body stays small enough for a guide of a thousand entries.
_WRITE_CHUNK = 200
# An `in.(id,id,...)` filter has to fit in a request URL.
_ID_CHUNK = 100

# Catalog reads never need the 1536-dimension embedding.
WIKI_ENTRY_LIST_COLUMNS = (
    "id",
    "workspace_id",
    "preferred_label",
    "canonical_slug",
    "definition",
    "significance",
    "category",
    "items",
    "pronunciation",
    "aliases",
    "prerequisites",
    "importance",
    "entry_kind",
    "status",
    "evidence",
    "origin",
    "created_at",
    "updated_at",
)


class WikiEntryRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int | None = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List wiki entries.

        ``limit=None`` keeps asking until a short page comes back. A larger
        limit is requested in pages of ``_REST_PAGE`` so a cap on one response
        cannot hide the rest.
        """
        filters = self._filters(workspace_id, status=status, search=search)
        if limit is None:
            return await self._every_page(filters, offset=offset)

        rows: list[dict[str, Any]] = []
        cursor = offset
        remaining = limit
        while remaining > 0:
            size = min(_REST_PAGE, remaining)
            page = await self._page(filters, limit=size, offset=cursor)
            rows.extend(page)
            if len(page) < size:
                return rows
            cursor += len(page)
            remaining -= len(page)
        return rows

    async def _every_page(self, filters: dict[str, str], *, offset: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor = offset
        while True:
            page = await self._page(filters, limit=_REST_PAGE, offset=cursor)
            rows.extend(page)
            if len(page) < _REST_PAGE:
                return rows
            cursor += len(page)

    async def _page(
        self,
        filters: dict[str, str],
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "wiki_entries",
            filters=filters,
            columns=",".join(WIKI_ENTRY_LIST_COLUMNS),
            order="preferred_label.asc",
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _filters(
        workspace_id: str,
        *,
        status: str | None,
        search: str | None,
    ) -> dict[str, str]:
        filters: dict[str, str] = {"workspace_id": f"eq.{workspace_id}"}
        if status:
            filters["status"] = f"eq.{status}"
        if search:
            filters["or"] = (
                f"(preferred_label.ilike.*{search}*,definition.ilike.*{search}*,significance.ilike.*{search}*)"
            )
        return filters

    async def get_for_workspace(
        self,
        wiki_entry_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        return await self.db.select_one(
            "wiki_entries",
            filters={
                "id": f"eq.{wiki_entry_id}",
                "workspace_id": f"eq.{workspace_id}",
            },
        )

    async def get_many(self, wiki_entry_ids: list[str]) -> list[dict[str, Any]]:
        if not wiki_entry_ids:
            return []

        rows: list[dict[str, Any]] = []
        for start in range(0, len(wiki_entry_ids), _ID_CHUNK):
            chunk = wiki_entry_ids[start : start + _ID_CHUNK]
            rows.extend(
                await self.db.select_many(
                    "wiki_entries",
                    filters={"id": f"in.({','.join(chunk)})"},
                    limit=len(chunk),
                ),
            )
        return rows

    async def insert_many(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []

        saved: list[dict[str, Any]] = []
        for start in range(0, len(rows), _WRITE_CHUNK):
            saved.extend(await self.db.insert("wiki_entries", rows[start : start + _WRITE_CHUNK]))
        return saved

    async def update(
        self,
        wiki_entry_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        rows = await self.db.update(
            "wiki_entries",
            filters={"id": f"eq.{wiki_entry_id}"},
            payload=payload,
        )
        return rows[0]

    async def list_disputes_for_workspace(
        self,
        workspace_id: str,
        *,
        status: str | None = "open",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        filters: dict[str, str] = {"workspace_id": f"eq.{workspace_id}"}

        if status:
            filters["status"] = f"eq.{status}"

        return await self.db.select_many(
            "wiki_disputes",
            filters=filters,
            order="created_at.desc",
            limit=limit,
        )
