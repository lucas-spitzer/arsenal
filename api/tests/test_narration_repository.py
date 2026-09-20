from __future__ import annotations

import asyncio
from typing import Any

from app.repositories.narration_segments import NarrationSegmentRepository


class _FakeRest:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"method": "many", "table": table, **kwargs})
        if kwargs.get("columns") == "model_id,voice_id":
            return [{"model_id": "eleven_v3", "voice_id": "voice-1"}]
        return [{"id": "narration-1"}]

    async def select_one(self, table: str, **kwargs: Any) -> dict[str, Any] | None:
        self.calls.append({"method": "one", "table": table, **kwargs})
        if table == "sources":
            return {"id": "source-1"}
        return {"id": "narration-1", "segment_id": "segment-1"}


def test_list_for_source_resolves_one_latest_variant_before_paging() -> None:
    db = _FakeRest()
    repository = NarrationSegmentRepository(db)  # type: ignore[arg-type]

    rows = asyncio.run(
        repository.list_for_source(
            "source-1",
            "workspace-1",
            "owner-1",
            limit=50,
            offset=10,
        )
    )

    assert rows == [{"id": "narration-1"}]
    variant_call = db.calls[1]
    assert variant_call["order"] == "updated_at.desc,id.desc"
    page_call = db.calls[2]
    assert page_call["filters"]["model_id"] == "eq.eleven_v3"
    assert page_call["filters"]["voice_id"] == "eq.voice-1"
    assert page_call["limit"] == 50
    assert page_call["offset"] == 10


def test_audio_lookup_is_bound_to_narration_row_id() -> None:
    db = _FakeRest()
    repository = NarrationSegmentRepository(db)  # type: ignore[arg-type]

    row = asyncio.run(
        repository.get_by_id(
            "source-1",
            "narration-1",
            "workspace-1",
            "owner-1",
        )
    )

    assert row is not None
    narration_call = db.calls[-1]
    assert narration_call["filters"] == {
        "id": "eq.narration-1",
        "source_id": "eq.source-1",
        "workspace_id": "eq.workspace-1",
    }
