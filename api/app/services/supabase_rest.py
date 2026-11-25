from typing import Any

import httpx

from app.config import Settings
from app.services.http_client import shared_client


class SupabaseRestError(Exception):
    """Raised when a Supabase REST request fails."""


class SupabaseRestClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"{settings.supabase_url}/rest/v1"

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.settings.supabase_service_role_key,
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if prefer:
            headers["Prefer"] = prefer

        return headers

    async def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any | None = None,
        prefer: str | None = None,
    ) -> Any:
        try:
            response = await shared_client().request(
                method,
                f"{self.base_url}/{table}",
                headers=self._headers(prefer=prefer),
                params=params,
                json=json_body,
            )
        except httpx.HTTPError as exc:
            raise SupabaseRestError("Supabase REST could not be reached.") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise SupabaseRestError(
                f"Supabase REST request failed ({response.status_code}): {detail}",
            )

        if response.status_code == 204 or not response.content:
            return None

        return response.json()

    async def select_one(
        self,
        table: str,
        *,
        filters: dict[str, str],
        columns: str = "*",
    ) -> dict[str, Any] | None:
        params = {"select": columns, "limit": "1", **filters}
        rows = await self.request("GET", table, params=params)

        if not rows:
            return None

        return rows[0]

    async def select_many(
        self,
        table: str,
        *,
        filters: dict[str, str] | None = None,
        columns: str = "*",
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": columns}

        if filters:
            params.update(filters)

        if order:
            params["order"] = order

        if limit is not None:
            params["limit"] = str(limit)

        if offset is not None:
            params["offset"] = str(offset)

        rows = await self.request("GET", table, params=params)
        return rows or []

    async def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = await self.request(
            "POST",
            table,
            json_body=payload,
            prefer="return=representation",
        )
        return rows or []

    async def update(
        self,
        table: str,
        *,
        filters: dict[str, str],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rows = await self.request(
            "PATCH",
            table,
            params=filters,
            json_body=payload,
            prefer="return=representation",
        )
        return rows or []

    async def delete(self, table: str, *, filters: dict[str, str]) -> None:
        await self.request("DELETE", table, params=filters)

    async def rpc(self, function_name: str, args: dict[str, Any]) -> Any:
        """Call a Postgres function via PostgREST (`/rest/v1/rpc/<fn>`)."""
        return await self.request("POST", f"rpc/{function_name}", json_body=args)
