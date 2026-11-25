import asyncio
from typing import Any

from app.models.atlas import AnswerSubmitRequest
from app.models.auth import CurrentUser
from app.services.atlas import AtlasService

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
    def __init__(self, *, existing: dict[str, Any] | None = None) -> None:
        self.existing = existing
        self.calls: list[str] = []
        self.attempt_updates: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def get_competition(self, workspace_id: str) -> dict[str, Any]:
        self.calls.append("get_competition")
        return {"workspace_id": workspace_id, "student_access": True, "ends_at": "2026-12-01T05:00:00+00:00"}

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


def _service(atlas: _Atlas) -> tuple[AtlasService, _Assessments]:
    assessments = _Assessments()
    service = AtlasService(
        atlas=atlas,  # type: ignore[arg-type]
        assessments=assessments,  # type: ignore[arg-type]
        sources=None,  # type: ignore[arg-type]
        lessons=None,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )
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
