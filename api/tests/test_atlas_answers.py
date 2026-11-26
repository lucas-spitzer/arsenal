import asyncio
from typing import Any

from app.repositories.atlas import AtlasRepository, _ANSWER_PAGE


def test_user_answers_page_past_the_thousand_row_cap() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.offsets: list[int] = []

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            assert table == "exam_answers"
            offset = int(kwargs["offset"])
            self.offsets.append(offset)
            assert kwargs["limit"] == _ANSWER_PAGE
            if offset == 0:
                return [{"id": index} for index in range(_ANSWER_PAGE)]
            return [{"id": _ANSWER_PAGE}, {"id": _ANSWER_PAGE + 1}]

    db = FakeDb()
    rows = asyncio.run(AtlasRepository(db).list_answers_for_user("ws-1", "user-1"))  # type: ignore[arg-type]

    assert db.offsets == [0, _ANSWER_PAGE]
    assert len(rows) == _ANSWER_PAGE + 2
