import asyncio
from typing import Any

from app.repositories.atlas import AtlasRepository, _READ_PAGE


def test_user_answers_page_past_the_thousand_row_cap() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.offsets: list[int] = []

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            assert table == "exam_answers"
            offset = int(kwargs["offset"])
            self.offsets.append(offset)
            assert kwargs["limit"] == _READ_PAGE
            if offset == 0:
                return [{"id": index} for index in range(_READ_PAGE)]
            return [{"id": _READ_PAGE}, {"id": _READ_PAGE + 1}]

    db = FakeDb()
    rows = asyncio.run(AtlasRepository(db).list_answers_for_user("ws-1", "user-1"))  # type: ignore[arg-type]

    assert db.offsets == [0, _READ_PAGE]
    assert len(rows) == _READ_PAGE + 2


def test_workspace_score_events_page_past_the_thousand_row_cap() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            self.calls.append({"table": table, **kwargs})
            offset = int(kwargs["offset"])
            if offset == 0:
                return [{"points": 1} for _ in range(_READ_PAGE)]
            return [{"points": 5}]

    db = FakeDb()
    rows = asyncio.run(AtlasRepository(db).list_score_events_for_workspace("ws-1"))  # type: ignore[arg-type]

    assert [call["table"] for call in db.calls] == ["score_events", "score_events"]
    assert [call["offset"] for call in db.calls] == [0, _READ_PAGE]
    assert sum(int(row["points"]) for row in rows) == _READ_PAGE + 5
