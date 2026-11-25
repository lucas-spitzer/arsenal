from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.services import supabase
from app.services.supabase import SupabaseAuthError, SupabaseService, clear_user_cache


class CountingClient:
    calls: list[str] = []
    session_ok = True

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        self.calls.append(url)
        if url.endswith("/auth/v1/user"):
            if not self.session_ok:
                return httpx.Response(401, json={})
            return httpx.Response(200, json={"id": "user-1", "email": "s@example.com"})
        return httpx.Response(
            200,
            json=[{"email": "s@example.com", "role": "student", "is_active": True}],
        )


def _service(monkeypatch: pytest.MonkeyPatch, *, session_ok: bool = True) -> SupabaseService:
    clear_user_cache()
    CountingClient.calls = []
    CountingClient.session_ok = session_ok
    monkeypatch.setattr(supabase, "shared_client", CountingClient)
    settings = SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable-key",
        supabase_service_role_key="service-key",
    )
    return SupabaseService(settings)  # type: ignore[arg-type]


def test_second_lookup_with_the_same_token_skips_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch)

    first = asyncio.run(service.get_current_user("token-a"))
    second = asyncio.run(service.get_current_user("token-a"))

    assert first == second
    assert len(CountingClient.calls) == 2


def test_cached_user_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(supabase.time, "monotonic", lambda: clock[0])

    asyncio.run(service.get_current_user("token-a"))
    clock[0] += supabase.USER_CACHE_SECONDS + 1
    asyncio.run(service.get_current_user("token-a"))

    assert len(CountingClient.calls) == 4


def test_failed_lookup_is_not_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch, session_ok=False)

    for _ in range(2):
        with pytest.raises(SupabaseAuthError):
            asyncio.run(service.get_current_user("token-bad"))

    assert len(CountingClient.calls) == 2
