from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_assessment_repository,
    get_knowledge_project_repository,
    get_quiz_result_repository,
)
from app.dependencies.workspace import require_workspace
from app.models.auth import CurrentUser
from app.models.quiz_result import QuizResultCreate, QuizResultResponse
from app.models.workspace import WorkspaceResponse
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_projects import KnowledgeProjectRepository
from app.repositories.quiz_results import QuizResultRepository
from app.services.quiz_results import QuizResultError, record_quiz_result

router = APIRouter(prefix="/workspaces", tags=["quiz-results"])


@router.get("/{workspace_id}/quiz-results", response_model=list[QuizResultResponse])
async def list_quiz_results(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    results: Annotated[QuizResultRepository, Depends(get_quiz_result_repository)],
) -> list[QuizResultResponse]:
    rows = await results.list_for_user(workspace.id, user.id)
    return [QuizResultResponse.model_validate(row) for row in rows]


@router.post(
    "/{workspace_id}/quiz-results",
    response_model=QuizResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quiz_result(
    payload: QuizResultCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    projects: Annotated[KnowledgeProjectRepository, Depends(get_knowledge_project_repository)],
    results: Annotated[QuizResultRepository, Depends(get_quiz_result_repository)],
) -> QuizResultResponse:
    try:
        row = await record_quiz_result(
            user_id=user.id,
            workspace_id=workspace.id,
            payload=payload,
            assessments=assessments,
            projects=projects,
            results=results,
        )
    except QuizResultError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.detail) from exc
    return QuizResultResponse.model_validate(row)
