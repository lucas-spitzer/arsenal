import pytest
from fastapi.testclient import TestClient


def test_hosted_api_is_mounted_at_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")

    from app.config import get_settings

    get_settings.cache_clear()
    import vercel_app

    client = TestClient(vercel_app.app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    direct = client.get("/health")
    assert direct.status_code == 200
    assert direct.json() == {"status": "ok"}

    me = client.get("/api/me")
    assert me.status_code == 401

    missing = client.post("/api/auth/email-code", json={})
    assert missing.status_code == 422
