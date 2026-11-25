import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.models.auth import CurrentUser
from app.services.atlas import AtlasError, AtlasService
from app.services.atlas_dashboard import (
    daily_activity,
    quiz_subject,
    subject_options,
    summary,
    weak_questions,
)

QUIZZES = {
    "q-book": {"id": "q-book", "source_id": "src-1", "lesson_id": None, "question": "Book question"},
    "q-class": {"id": "q-class", "source_id": None, "lesson_id": "les-1", "question": "Class question"},
    "q-class-2": {"id": "q-class-2", "source_id": None, "lesson_id": "les-1", "question": "Second class question"},
    "q-orphan": {"id": "q-orphan", "source_id": None, "lesson_id": None, "question": "Orphan"},
}
NAMES = {("source", "src-1"): "Warfighting", ("lesson", "les-1"): "Land Navigation"}


def test_lesson_wins_over_source() -> None:
    assert quiz_subject({"lesson_id": "les-1", "source_id": "src-1"}) == ("lesson", "les-1")
    assert quiz_subject({"lesson_id": None, "source_id": "src-1"}) == ("source", "src-1")
    assert quiz_subject({"lesson_id": None, "source_id": None}) is None


def test_subject_options_list_answered_subjects_by_name() -> None:
    answers = [{"quiz_id": "q-class"}, {"quiz_id": "q-book"}, {"quiz_id": "q-class-2"}, {"quiz_id": "q-orphan"}]
    assert subject_options(answers, QUIZZES, NAMES) == [
        {"subject_kind": "lesson", "subject_id": "les-1", "subject_name": "Land Navigation"},
        {"subject_kind": "source", "subject_id": "src-1", "subject_name": "Warfighting"},
    ]


def test_summary_scopes_to_one_subject() -> None:
    answers = [
        {"quiz_id": "q-book", "is_correct": True},
        {"quiz_id": "q-class", "is_correct": False},
        {"quiz_id": "q-class", "is_correct": True},
    ]
    progress = [
        {"quiz_id": "q-book", "mastered_at": "2026-11-01T00:00:00Z"},
        {"quiz_id": "q-class", "mastered_at": None},
    ]
    events = [{"quiz_id": "q-book", "points": 5}, {"quiz_id": "q-class", "points": 5}]

    everything = summary(answers=answers, progress=progress, events=events, quizzes=QUIZZES, scope=None)
    assert everything["lifetime_ap"] == 10
    assert everything["concepts_mastered"] == 1
    assert everything["total_questions"] == 3
    assert everything["questions_answered"] == 3
    assert everything["accuracy"] == 67

    lesson = summary(answers=answers, progress=progress, events=events, quizzes=QUIZZES, scope=("lesson", "les-1"))
    assert lesson["lifetime_ap"] == 5
    assert lesson["concepts_mastered"] == 0
    assert lesson["total_questions"] == 2
    assert lesson["questions_answered"] == 2
    assert lesson["accuracy"] == 50


def test_weak_questions_skip_mastered_and_sort_by_misses() -> None:
    progress = [
        {"quiz_id": "q-book", "correct_count": 5, "incorrect_count": 4, "mastered_at": "2026-11-01T00:00:00Z"},
        {"quiz_id": "q-class", "correct_count": 1, "incorrect_count": 2, "mastered_at": None},
        {"quiz_id": "q-class-2", "correct_count": 0, "incorrect_count": 2, "mastered_at": None},
        {"quiz_id": "q-orphan", "correct_count": 0, "incorrect_count": 9, "mastered_at": None},
    ]
    rows = weak_questions(progress=progress, quizzes=QUIZZES, names=NAMES, scope=None)
    assert [row["quiz_id"] for row in rows] == ["q-class-2", "q-class"]
    assert rows[0]["subject_name"] == "Land Navigation"

    assert weak_questions(progress=progress, quizzes=QUIZZES, names=NAMES, scope=("source", "src-1")) == []


def test_daily_activity_buckets_by_local_day() -> None:
    # 02:30 UTC on Nov 25 is still Nov 24 in New York.
    answers = [
        {"quiz_id": "q-book", "is_correct": True, "submitted_at": "2026-11-25T02:30:00+00:00"},
        {"quiz_id": "q-book", "is_correct": False, "submitted_at": "2026-11-25T15:00:00+00:00"},
    ]
    events = [{"quiz_id": "q-book", "points": 5, "created_at": "2026-11-25T02:30:00+00:00"}]
    now = datetime(2026, 11, 25, 16, 0, tzinfo=UTC)

    local = daily_activity(
        answers=answers, events=events, quizzes=QUIZZES, scope=None, tz="America/New_York", now=now, days=3
    )
    assert [row["day"] for row in local] == ["2026-11-23", "2026-11-24", "2026-11-25"]
    assert local[1] == {"day": "2026-11-24", "answered": 1, "correct": 1, "points": 5}
    assert local[2] == {"day": "2026-11-25", "answered": 1, "correct": 0, "points": 0}

    utc = daily_activity(answers=answers, events=events, quizzes=QUIZZES, scope=None, tz="UTC", now=now, days=3)
    assert utc[2] == {"day": "2026-11-25", "answered": 2, "correct": 1, "points": 5}


class _Atlas:
    def __init__(self) -> None:
        self.users: list[str] = []

    async def get_competition(self, workspace_id: str) -> dict[str, Any]:
        return {"workspace_id": workspace_id, "student_access": True, "ends_at": "2026-12-01T05:00:00+00:00"}

    async def list_answers_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        self.users.append(user_id)
        return [{"quiz_id": "q-class", "is_correct": True, "submitted_at": "2026-11-24T12:00:00+00:00"}]

    async def list_progress_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return []

    async def list_score_events_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return [{"quiz_id": "q-class", "points": 5, "created_at": "2026-11-24T12:00:00+00:00"}]

    async def list_answers_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return [
            {"user_id": "s1", "quiz_id": "q-class", "is_correct": True, "submitted_at": "2026-11-24T12:00:00+00:00"},
            {"user_id": "s2", "quiz_id": "q-class", "is_correct": False, "submitted_at": "2026-11-24T13:00:00+00:00"},
            {"user_id": "obs", "quiz_id": "q-class", "is_correct": False, "submitted_at": "2026-11-24T13:00:00+00:00"},
        ]

    async def list_progress_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return [
            {"user_id": "s1", "quiz_id": "q-class", "correct_count": 1, "incorrect_count": 1, "mastered_at": None},
            {"user_id": "s2", "quiz_id": "q-class", "correct_count": 0, "incorrect_count": 2, "mastered_at": None},
            {"user_id": "obs", "quiz_id": "q-class", "correct_count": 0, "incorrect_count": 7, "mastered_at": None},
        ]

    async def list_score_events_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return [
            {"user_id": "s1", "quiz_id": "q-class", "points": 5, "created_at": "2026-11-24T12:00:00+00:00"},
            {"user_id": "obs", "quiz_id": "q-class", "points": 5, "created_at": "2026-11-24T12:00:00+00:00"},
        ]


class _Assessments:
    async def list_quizzes(self, workspace_id: str, *, limit: int, offset: int) -> list[dict[str, Any]]:
        return list(QUIZZES.values()) if offset == 0 else []


class _Sources:
    async def list_for_workspace(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        return [{"id": "src-1", "filename": "Warfighting.pdf", "source_metadata": {}}]


class _Lessons:
    async def list_with_children(self, workspace_id: str) -> list[dict[str, Any]]:
        return [{"id": "les-1", "title": "Land Navigation"}]


def _service() -> tuple[AtlasService, _Atlas]:
    atlas = _Atlas()
    service = AtlasService(
        atlas=atlas,  # type: ignore[arg-type]
        assessments=_Assessments(),  # type: ignore[arg-type]
        sources=_Sources(),  # type: ignore[arg-type]
        lessons=_Lessons(),  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )
    return service, atlas


def _dashboard(service: AtlasService, user: CurrentUser, **kwargs: Any):
    return asyncio.run(
        service.dashboard(
            user=user,
            workspace_id="ws-1",
            owner_id="owner-1",
            user_id=kwargs.get("user_id"),
            subject_kind=kwargs.get("subject_kind"),
            subject_id=kwargs.get("subject_id"),
            tz="UTC",
        )
    )


def test_student_cannot_open_another_students_dashboard() -> None:
    service, _atlas = _service()
    student = CurrentUser(id="student-1", email="s@example.com", role="student")
    with pytest.raises(AtlasError) as caught:
        _dashboard(service, student, user_id="student-2")
    assert caught.value.status_code == 403


def test_admin_can_open_a_students_dashboard_scoped_to_a_class() -> None:
    service, atlas = _service()
    admin = CurrentUser(id="admin-1", email="a@example.com", role="admin")
    result = _dashboard(service, admin, user_id="student-2", subject_kind="lesson", subject_id="les-1")
    assert atlas.users == ["student-2"]
    assert result.user_id == "student-2"
    assert result.summary.lifetime_ap == 5
    assert result.summary.total_questions == 2
    assert [subject.subject_name for subject in result.subjects] == ["Land Navigation"]


def test_platoon_dashboard_combines_students_and_skips_observers() -> None:
    service, _atlas = _service()

    async def observers() -> set[str]:
        return {"obs"}

    service._observer_user_ids = observers  # type: ignore[method-assign]
    admin = CurrentUser(id="admin-1", email="a@example.com", role="admin")
    result = _dashboard(service, admin, user_id="platoon")

    assert result.user_id == "platoon"
    assert result.summary.lifetime_ap == 5
    assert result.summary.questions_answered == 2
    assert result.summary.accuracy == 50
    assert result.summary.total_questions == 3 * 2
    assert len(result.weak_questions) == 1
    assert result.weak_questions[0].correct_count == 1
    assert result.weak_questions[0].incorrect_count == 3


def test_student_cannot_open_the_platoon_dashboard() -> None:
    service, _atlas = _service()
    student = CurrentUser(id="student-1", email="s@example.com", role="student")
    with pytest.raises(AtlasError) as caught:
        _dashboard(service, student, user_id="platoon")
    assert caught.value.status_code == 403


def test_unknown_timezone_falls_back_to_utc() -> None:
    now = datetime(2026, 11, 25, 16, 0, tzinfo=UTC)
    rows = daily_activity(answers=[], events=[], quizzes=QUIZZES, scope=None, tz="Mars/Base", now=now, days=1)
    assert rows == [{"day": "2026-11-25", "answered": 0, "correct": 0, "points": 0}]
