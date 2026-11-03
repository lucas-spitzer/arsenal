from typing import Any

from app.knowledge.answer_pool import ShownAnswerError, cited_wiki_id, grade_shown_answer
from app.models.quiz_result import QuizResultCreate
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_projects import KnowledgeProjectRepository
from app.repositories.quiz_results import QuizResultRepository

UNASSIGNED_BATCH = "Unassigned"


class QuizResultError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _optional_id(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def assemble_quiz_result(payload: QuizResultCreate, quizzes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grade a finished batch. Raises QuizResultError when the submission does not match the questions."""
    quiz_ids = [answer.quiz_id for answer in payload.answers]
    if len(quiz_ids) != len(set(quiz_ids)):
        raise QuizResultError("Each question can be answered once.")

    by_id = {str(quiz["id"]): quiz for quiz in quizzes}
    missing = [quiz_id for quiz_id in quiz_ids if quiz_id not in by_id]
    if missing:
        raise QuizResultError("A question in this quiz is not in the workspace.")

    graded: list[dict[str, Any]] = []
    for answer in payload.answers:
        quiz = by_id[answer.quiz_id]
        project_id = _optional_id(quiz.get("knowledge_project_id"))
        source_id = _optional_id(quiz.get("source_id"))
        if project_id != payload.knowledge_project_id:
            raise QuizResultError("These questions are not in that batch.")
        if source_id != payload.source_id:
            raise QuizResultError("These questions are not in that batch.")
        try:
            correct, right = grade_shown_answer(
                quiz,
                question=answer.question,
                options=answer.options,
                selected_index=answer.selected_index,
            )
        except ShownAnswerError as exc:
            raise QuizResultError(str(exc)) from exc
        kind = str(quiz.get("subtype") or quiz.get("question_type") or "")
        stored_question = str(quiz.get("question") or answer.question).strip()
        shown_question = answer.question.strip() if kind in {"true_false", "true_false_correction"} else stored_question
        graded.append(
            {
                "quiz_id": answer.quiz_id,
                "wiki_id": cited_wiki_id(quiz),
                "question": shown_question,
                "selected": answer.options[answer.selected_index],
                "answer": right,
                "correct": correct,
            }
        )
    return graded


async def record_quiz_result(
    *,
    user_id: str,
    workspace_id: str,
    payload: QuizResultCreate,
    assessments: AssessmentRepository,
    projects: KnowledgeProjectRepository,
    results: QuizResultRepository,
) -> dict[str, Any]:
    rows = await assessments.list_quizzes_by_ids(
        workspace_id,
        [answer.quiz_id for answer in payload.answers],
    )
    graded = assemble_quiz_result(payload, rows)
    if payload.knowledge_project_id:
        project = await projects.get_in_workspace(payload.knowledge_project_id, workspace_id)
        if not project:
            raise QuizResultError("That batch is not in this workspace.")
        title = str(project.get("title") or UNASSIGNED_BATCH)
    else:
        title = UNASSIGNED_BATCH
    correct_count = sum(1 for answer in graded if answer["correct"])
    return await results.insert(
        {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "knowledge_project_id": payload.knowledge_project_id,
            "source_id": payload.source_id,
            "title": title,
            "scope": payload.scope,
            "correct_count": correct_count,
            "question_count": len(graded),
            "answers": graded,
        }
    )
