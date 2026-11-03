from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.knowledge.answer_pool import ShownAnswerError, grade_shown_answer
from app.models.auth import CurrentUser
from app.models.quiz_result import QuizResultCreate
from app.models.workspace import WorkspaceResponse
from app.repositories.quiz_results import QuizResultRepository
from app.routers.quiz_results import list_quiz_results
from app.services.quiz_results import QuizResultError, assemble_quiz_result, record_quiz_result


def _workspace() -> WorkspaceResponse:
    now = datetime.now(UTC)
    return WorkspaceResponse(
        id="ws-1",
        owner_id="owner-1",
        name="The Basic School",
        slug="the-basic-school",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def _quiz(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "quiz-1",
        "workspace_id": "ws-1",
        "source_id": "src-1",
        "knowledge_project_id": "proj-1",
        "question": "What resists every action?",
        "question_type": "multiple_choice",
        "subtype": "multiple_choice",
        "options": ["Friction", "Chance"],
        "correct_answer": "Friction",
        "answer_pool": {
            "correct": ["Friction", "The force that resists action"],
            "distractors": [{"text": "Chance", "misconception": ""}],
            "show_count": 2,
        },
        "citations": [{"uri": "wiki://wiki-friction"}],
    }
    row.update(overrides)
    return row


def _payload(**overrides: Any) -> QuizResultCreate:
    body: dict[str, Any] = {
        "knowledge_project_id": "proj-1",
        "source_id": "src-1",
        "scope": "one_per_term",
        "answers": [
            {
                "quiz_id": "quiz-1",
                "question": "What resists every action?",
                "options": ["Chance", "The force that resists action"],
                "selected_index": 1,
            }
        ],
    }
    body.update(overrides)
    return QuizResultCreate.model_validate(body)


def test_pool_selection_is_correct_when_the_picked_text_is_a_correct_answer() -> None:
    correct, right = grade_shown_answer(
        _quiz(),
        question="What resists every action?",
        options=["Chance", "The force that resists action"],
        selected_index=1,
    )
    assert correct is True
    assert right == "The force that resists action"


def test_pool_miss_stores_a_correct_answer() -> None:
    correct, right = grade_shown_answer(
        _quiz(),
        question="What resists every action?",
        options=["Chance", "The force that resists action"],
        selected_index=0,
    )
    assert correct is False
    assert right == "The force that resists action"


def test_true_false_stem_must_belong_to_the_pool() -> None:
    quiz = _quiz(
        subtype="true_false_correction",
        question_type="true_false_correction",
        answer_pool={
            "correct": ["Friction resists every action."],
            "distractors": [{"text": "Chance can be removed.", "misconception": ""}],
            "show_count": 2,
        },
    )
    correct, right = grade_shown_answer(
        quiz,
        question="Chance can be removed.",
        options=["True", "False"],
        selected_index=1,
    )
    assert correct is True
    assert right == "False"
    with pytest.raises(ShownAnswerError):
        grade_shown_answer(
            quiz,
            question="A statement that was never written.",
            options=["True", "False"],
            selected_index=0,
        )


def test_assemble_keeps_a_correct_answer_and_the_wiki_id() -> None:
    graded = assemble_quiz_result(_payload(), [_quiz()])
    assert graded[0]["correct"] is True
    assert graded[0]["wiki_id"] == "wiki-friction"
    assert graded[0]["answer"] == "The force that resists action"


def test_assemble_rejects_a_question_from_another_batch() -> None:
    with pytest.raises(QuizResultError):
        assemble_quiz_result(_payload(), [_quiz(knowledge_project_id="proj-2")])


class _Assessments:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def list_quizzes_by_ids(self, workspace_id: str, quiz_ids: list[str]) -> list[dict[str, Any]]:
        wanted = set(quiz_ids)
        return [row for row in self.rows if row["workspace_id"] == workspace_id and row["id"] in wanted]


class _Projects:
    async def get_in_workspace(self, project_id: str, workspace_id: str) -> dict[str, Any] | None:
        if project_id == "proj-1" and workspace_id == "ws-1":
            return {"id": "proj-1", "title": "Chapter 1", "source_id": "src-1"}
        return None


class _Results:
    def __init__(self) -> None:
        self.inserted: dict[str, Any] | None = None
        self.listed: tuple[str, str] | None = None

    async def insert(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.inserted = payload
        return {"id": "result-1", "completed_at": "2026-11-02T18:00:00+00:00", **payload}

    async def list_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        self.listed = (workspace_id, user_id)
        return []


def test_record_stores_the_caller_and_the_batch_title() -> None:
    results = _Results()
    row = asyncio.run(
        record_quiz_result(
            user_id="student-9",
            workspace_id="ws-1",
            payload=_payload(),
            assessments=_Assessments([_quiz()]),  # type: ignore[arg-type]
            projects=_Projects(),  # type: ignore[arg-type]
            results=results,  # type: ignore[arg-type]
        )
    )
    assert results.inserted is not None
    assert results.inserted["user_id"] == "student-9"
    assert results.inserted["title"] == "Chapter 1"
    assert row["correct_count"] == 1
    assert row["answers"][0]["correct"] is True


def test_list_is_scoped_to_the_caller() -> None:
    class _Db:
        def __init__(self) -> None:
            self.filters: dict[str, str] | None = None

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            assert table == "quiz_results"
            self.filters = kwargs["filters"]
            return []

    db = _Db()
    repo = QuizResultRepository(db)  # type: ignore[arg-type]
    asyncio.run(repo.list_for_user("ws-1", "student-9"))
    assert db.filters == {
        "workspace_id": "eq.ws-1",
        "user_id": "eq.student-9",
    }

    results = _Results()
    user = CurrentUser(id="student-9", email="student@example.com", role="student")
    asyncio.run(list_quiz_results(_workspace(), user, results))  # type: ignore[arg-type]
    assert results.listed == ("ws-1", "student-9")
