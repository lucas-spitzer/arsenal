from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.services.supabase import SupabaseService, SupabaseUserNotApprovedError


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable-key",
        supabase_service_role_key="service-key",
    )


class RecordingClient:
    posts: list[tuple[str, dict[str, object], dict[str, str]]] = []
    approved: list[dict[str, object]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def __aenter__(self) -> RecordingClient:
        return self

    async def __aexit__(self, *args: object) -> bool:
        del args
        return False

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        del url, kwargs
        return httpx.Response(200, json=list(self.approved))

    async def post(self, url: str, **kwargs: object) -> httpx.Response:
        headers = kwargs.get("headers")
        body = kwargs.get("json")
        self.posts.append(
            (
                url,
                body if isinstance(body, dict) else {},
                headers if isinstance(headers, dict) else {},
            )
        )
        return httpx.Response(200, json={})


def _install(monkeypatch: pytest.MonkeyPatch, approved: list[dict[str, object]]) -> None:
    RecordingClient.posts = []
    RecordingClient.approved = approved
    monkeypatch.setattr("app.services.supabase.httpx.AsyncClient", RecordingClient)


def test_unknown_email_does_not_send_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, [])
    service = SupabaseService(_settings())  # type: ignore[arg-type]

    with pytest.raises(SupabaseUserNotApprovedError):
        asyncio.run(service.send_email_code("nope@example.com"))

    assert RecordingClient.posts == []


def test_approved_email_sends_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [{"email": "student@example.com", "role": "student", "is_active": True}],
    )
    service = SupabaseService(_settings())  # type: ignore[arg-type]

    asyncio.run(service.send_email_code("  student@example.com  "))

    assert len(RecordingClient.posts) == 1
    url, body, headers = RecordingClient.posts[0]
    assert url == "https://example.supabase.co/auth/v1/otp"
    assert body == {"email": "student@example.com", "create_user": True}
    assert headers["Authorization"] == "Bearer publishable-key"
    assert headers["apikey"] == "publishable-key"
