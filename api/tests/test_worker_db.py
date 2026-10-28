from typing import Any

import httpx
import pytest

from app.worker.db import NDR_SEGMENT_COLUMNS, WorkerDatabase

_TIMEOUT = (
    '{"code":"57014","details":null,"hint":null,'
    '"message":"canceling statement due to statement timeout"}'
)


class _ScriptedHttp:
    def __init__(self, responses: list[httpx.Response], calls: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls = calls

    def __enter__(self) -> "_ScriptedHttp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def _database(
    monkeypatch: pytest.MonkeyPatch, responses: list[httpx.Response]
) -> tuple[WorkerDatabase, list[dict[str, Any]]]:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key")
    monkeypatch.setattr("app.worker.db.time.sleep", lambda _: None)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.worker.db.httpx.Client",
        lambda **_kwargs: _ScriptedHttp(responses, calls),
    )
    return WorkerDatabase(), calls


def test_get_retries_statement_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    db, calls = _database(
        monkeypatch,
        [httpx.Response(500, text=_TIMEOUT), httpx.Response(200, json=[{"id": "p1"}])],
    )

    rows = db.list_ndr_segments_for_source("src-1")

    assert rows == [{"id": "p1"}]
    assert len(calls) == 2
    assert calls[0]["params"]["select"] == NDR_SEGMENT_COLUMNS
    assert "embedding" not in NDR_SEGMENT_COLUMNS


def test_writes_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    db, calls = _database(monkeypatch, [httpx.Response(500, text=_TIMEOUT)])

    with pytest.raises(RuntimeError, match="57014"):
        db.create_stage_run({"status": "running"})
    assert len(calls) == 1
