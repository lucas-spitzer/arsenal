from typing import Any

import httpx

from app.config import Settings


class SupabaseStorageError(Exception):
    """Raised when a Supabase Storage request fails."""


class SupabaseStorageClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"{settings.supabase_url}/storage/v1"

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.settings.supabase_service_role_key,
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
        }

        if content_type:
            headers["Content-Type"] = content_type

        return headers

    async def upload(
        self,
        *,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        upsert: bool = False,
    ) -> dict[str, Any]:
        headers = self._headers(content_type=content_type)

        if upsert:
            headers["x-upsert"] = "true"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.base_url}/object/{bucket}/{path}",
                    headers=headers,
                    content=content,
                )
        except httpx.HTTPError as exc:
            raise SupabaseStorageError("Supabase Storage could not be reached.") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise SupabaseStorageError(
                f"Supabase Storage upload failed ({response.status_code}): {detail}",
            )

        return response.json()

    async def delete(self, *, bucket: str, path: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.delete(
                    f"{self.base_url}/object/{bucket}/{path}",
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise SupabaseStorageError("Supabase Storage could not be reached.") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise SupabaseStorageError(
                f"Supabase Storage delete failed ({response.status_code}): {detail}",
            )

    async def delete_paths(self, *, bucket: str, paths: list[str]) -> None:
        """Delete object keys. A missing object is success."""
        unique = list(dict.fromkeys(path for path in paths if path and path != "pending"))
        if not unique:
            return

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                for start in range(0, len(unique), 1000):
                    batch = unique[start : start + 1000]
                    response = await client.request(
                        "DELETE",
                        f"{self.base_url}/object/{bucket}",
                        headers=self._headers(content_type="application/json"),
                        json={"prefixes": batch},
                    )
                    if response.status_code in {200, 204, 404}:
                        continue
                    if response.status_code == 400:
                        for path in batch:
                            await self._delete_if_present(bucket=bucket, path=path)
                        continue
                    detail = response.text.strip() or response.reason_phrase
                    raise SupabaseStorageError(
                        f"Supabase Storage delete failed ({response.status_code}): {detail}",
                    )
        except httpx.HTTPError as exc:
            raise SupabaseStorageError("Supabase Storage could not be reached.") from exc

    async def _delete_if_present(self, *, bucket: str, path: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.delete(
                    f"{self.base_url}/object/{bucket}/{path}",
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise SupabaseStorageError("Supabase Storage could not be reached.") from exc

        if response.status_code in {200, 204, 400, 404}:
            return

        detail = response.text.strip() or response.reason_phrase
        raise SupabaseStorageError(
            f"Supabase Storage delete failed ({response.status_code}): {detail}",
        )

    async def create_signed_url(
        self,
        *,
        bucket: str,
        path: str,
        expires_in: int = 3600,
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/object/sign/{bucket}/{path}",
                    headers={
                        **self._headers(content_type="application/json"),
                    },
                    json={"expiresIn": expires_in},
                )
        except httpx.HTTPError as exc:
            raise SupabaseStorageError("Supabase Storage could not be reached.") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise SupabaseStorageError(
                f"Supabase Storage sign failed ({response.status_code}): {detail}",
            )

        payload = response.json()
        signed_url = payload.get("signedURL")

        if not isinstance(signed_url, str):
            raise SupabaseStorageError("Supabase Storage sign response was invalid.")

        if signed_url.startswith("http"):
            return signed_url

        return f"{self.settings.supabase_url}/storage/v1{signed_url}"

    async def download(self, *, bucket: str, path: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.get(
                    f"{self.base_url}/object/{bucket}/{path}",
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise SupabaseStorageError("Supabase Storage could not be reached.") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise SupabaseStorageError(
                f"Supabase Storage download failed ({response.status_code}): {detail}",
            )

        return response.content
