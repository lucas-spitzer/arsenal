import asyncio
from datetime import UTC, datetime
from typing import Any

from app.models.atlas import AnswerSubmitRequest, LeaderboardEntry
from app.models.auth import CurrentUser
from app.services.atlas import AtlasService, competition_closed

ENDS_AT = "2026-12-01T03:00:00+00:00"
BEFORE_END = datetime(2026, 11, 30, 12, 0, tzinfo=UTC)
AFTER_END = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)

QUIZ = {
    "id": "q-1",
    "workspace_id": "ws-1",
    "question": "Capital of France?",
    "options": ["Paris", "Rome"],
    "correct_answer": "Paris",
    "explanation": "It is Paris.",
}
STUDENT = CurrentUser(id="student-1", email="s@example.com", role="student")


class _Atlas:
    def __init__(self, *, existing: dict[str, Any] | None = None, lose_freeze_race: bool = False) -> None:
        self.existing = existing
        self.lose_freeze_race = lose_freeze_race
        self.calls: list[str] = []
        self.attempt_updates: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.competition: dict[str, Any] = {
            "workspace_id": "ws-1",
            "student_access": True,
            "ends_at": ENDS_AT,
            "finalized_at": None,
            "final_standings": None,
        }

    async def get_competition(self, workspace_id: str) -> dict[str, Any]:
        self.calls.append("get_competition")
        return dict(self.competition)

    async def finalize_competition_if_open(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.calls.append("finalize_competition_if_open")
        if self.lose_freeze_race:
            self.competition.update(payload)
            return None
        if self.competition["finalized_at"]:
            return None
        self.competition.update(payload)
        return dict(self.competition)

    async def get_attempt(self, attempt_id: str, workspace_id: str, user_id: str) -> dict[str, Any]:
        self.calls.append("get_attempt")
        return {
            "id": attempt_id,
            "status": "in_progress",
            "correct_count": 3,
            "points_earned": 20,
            "questions": [
                {"quiz_id": "q-0", "question": "Earlier", "options": ["A", "B"]},
                {"quiz_id": "q-1", "question": QUIZ["question"], "options": QUIZ["options"]},
            ],
        }

    async def get_answer(self, attempt_id: str, quiz_id: str) -> dict[str, Any] | None:
        self.calls.append("get_answer")
        return self.existing

    async def get_progress(self, user_id: str, quiz_id: str) -> dict[str, Any] | None:
        self.calls.append("get_progress")
        return None

    async def upsert_progress(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("upsert_progress")
        return payload

    async def insert_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("insert_answer")
        return {"id": "answer-1", **payload}

    async def insert_score_events(self, rows: list[dict[str, Any]]) -> None:
        self.calls.append("insert_score_events")
        self.events.extend(rows)

    async def update_attempt(self, attempt_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("update_attempt")
        self.attempt_updates.append(payload)
        return {"id": attempt_id, **payload}

    async def list_answers_for_attempt(self, attempt_id: str) -> list[dict[str, Any]]:
        raise AssertionError("submit should not re-read every answer in the exam")

    async def list_score_points_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        self.calls.append("list_score_points_for_user")
        return [{"points": 100}, *({"points": row["points"]} for row in self.events)]


class _Assessments:
    def __init__(self) -> None:
        self.calls = 0

    async def get_quiz(self, quiz_id: str, workspace_id: str) -> dict[str, Any]:
        self.calls += 1
        return QUIZ


def _service(atlas: _Atlas, *, now: datetime = BEFORE_END) -> tuple[AtlasService, _Assessments]:
    assessments = _Assessments()
    service = AtlasService(
        atlas=atlas,  # type: ignore[arg-type]
        assessments=assessments,  # type: ignore[arg-type]
        sources=None,  # type: ignore[arg-type]
        lessons=None,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        clock=lambda: now,
    )

    async def standings(workspace_id: str) -> list[LeaderboardEntry]:
        atlas.calls.append("build_leaderboard")
        return [
            LeaderboardEntry(
                rank=1, user_id="student-1", name="Student", lifetime_ap=120, concepts_mastered=2, accuracy=80
            )
        ]

    service._build_leaderboard = standings  # type: ignore[method-assign]
    return service, assessments


def _submit(service: AtlasService, selected_index: int) -> Any:
    return asyncio.run(
        service.submit_exam_answer(
            user=STUDENT,
            workspace_id="ws-1",
            attempt_id="attempt-1",
            payload=AnswerSubmitRequest(
                quiz_id="q-1",
                question=QUIZ["question"],
                options=QUIZ["options"],
                selected_index=selected_index,
            ),
        )
    )


def test_correct_answer_adds_to_the_attempt_row_totals() -> None:
    atlas = _Atlas()
    service, assessments = _service(atlas)

    result = _submit(service, 0)

    assert result.correct is True
    assert result.points_total > 0
    assert result.attempt_correct_count == 4
    assert result.attempt_points_earned == 20 + result.points_total
    assert atlas.attempt_updates == [{"correct_count": 4, "points_earned": 20 + result.points_total}]
    assert result.lifetime_ap == 100 + result.points_total
    assert assessments.calls == 1
    assert atlas.calls.count("get_progress") == 1


def test_wrong_answer_keeps_attempt_points_and_writes_no_events() -> None:
    atlas = _Atlas()
    service, _ = _service(atlas)

    result = _submit(service, 1)

    assert result.correct is False
    assert result.right_answer == "Paris"
    assert atlas.attempt_updates == [{"correct_count": 3, "points_earned": 20}]
    assert "insert_score_events" not in atlas.calls
    assert result.lifetime_ap == 100


def test_repeat_submit_returns_the_saved_result_without_writing() -> None:
    atlas = _Atlas(existing={"is_correct": True, "points_awarded": 10, "feedback": None})
    service, _ = _service(atlas)

    result = _submit(service, 0)

    assert result.correct is True
    assert result.points_total == 10
    assert result.newly_mastered is False
    assert not {"upsert_progress", "insert_answer", "update_attempt"} & set(atlas.calls)


def test_competition_closes_at_its_end_time_or_when_frozen() -> None:
    open_row = {"ends_at": ENDS_AT, "finalized_at": None}
    assert competition_closed(open_row, BEFORE_END) is False
    assert competition_closed(open_row, AFTER_END) is True
    assert competition_closed({"ends_at": "2026-12-01T03:00:00Z"}, AFTER_END) is True
    assert competition_closed({"ends_at": ENDS_AT, "finalized_at": "2026-11-29T00:00:00Z"}, BEFORE_END) is True


def test_answer_before_the_end_time_still_scores_and_does_not_freeze() -> None:
    atlas = _Atlas()
    service, _ = _service(atlas, now=BEFORE_END)

    result = _submit(service, 0)

    assert result.points_total > 0
    assert "insert_score_events" in atlas.calls
    assert "finalize_competition_if_open" not in atlas.calls


def test_answer_after_the_end_time_is_graded_but_earns_no_points() -> None:
    atlas = _Atlas()
    service, _ = _service(atlas, now=AFTER_END)

    result = _submit(service, 0)

    assert result.correct is True
    assert result.points_total == 0
    assert result.points_awarded == []
    assert result.newly_mastered is False
    assert result.lifetime_ap == 100
    assert "insert_score_events" not in atlas.calls
    assert {"upsert_progress", "insert_answer"} <= set(atlas.calls)
    assert atlas.attempt_updates == [{"correct_count": 4, "points_earned": 20}]


def test_first_read_after_the_end_time_freezes_the_standings_once() -> None:
    atlas = _Atlas()
    service, _ = _service(atlas, now=AFTER_END)

    first = asyncio.run(service.leaderboard(user=STUDENT, workspace_id="ws-1"))
    second = asyncio.run(service.leaderboard(user=STUDENT, workspace_id="ws-1"))

    assert first.finalized is True
    assert second.finalized is True
    assert [entry.lifetime_ap for entry in second.entries] == [120]
    assert atlas.calls.count("finalize_competition_if_open") == 1
    assert atlas.calls.count("build_leaderboard") == 1


def test_losing_the_freeze_race_reads_the_snapshot_the_other_request_wrote() -> None:
    atlas = _Atlas(lose_freeze_race=True)
    service, _ = _service(atlas, now=AFTER_END)

    board = asyncio.run(service.leaderboard(user=STUDENT, workspace_id="ws-1"))

    assert board.finalized is True
    assert [entry.lifetime_ap for entry in board.entries] == [120]
