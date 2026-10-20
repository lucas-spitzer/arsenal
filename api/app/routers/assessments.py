from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import Settings, get_settings
from app.access import can_read_library
from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_assessment_repository,
    get_knowledge_project_repository,
    get_supabase_storage_client,
    get_workspace_repository,
)
from app.dependencies.workspace import require_workspace
from app.knowledge.visuals import storage_path_of, visual_for_response
from app.models.assessment import (
    FlashcardResponse,
    QuizResponse,
    ScenarioResponse,
)
from app.models.auth import CurrentUser
from app.models.knowledge import KnowledgeRunTitle
from app.models.workspace import WorkspaceResponse
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_projects import KnowledgeProjectRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.supabase_storage import SupabaseStorageClient

router = APIRouter(tags=["assessments"])


async def _readable_row(
    row: dict[str, Any] | None,
    user: CurrentUser,
    workspaces: WorkspaceRepository,
) -> dict[str, Any] | None:
    if not row:
        return None
    workspace = await workspaces.get(str(row["workspace_id"]))
    if not workspace or not can_read_library(
        user,
        str(workspace["owner_id"]),
        workspace_name=str(workspace.get("name") or ""),
    ):
        return None
    return row


async def _with_signed_visuals(
    rows: list[dict[str, Any]],
    storage: SupabaseStorageClient,
    settings: Settings,
) -> list[dict[str, Any]]:
    paths = {
        path
        for row in rows
        if (path := storage_path_of(row.get("visual") if isinstance(row.get("visual"), dict) else None))
    }
    signed: dict[str, str] = {}
    for path in paths:
        signed[path] = await storage.create_signed_url(
            bucket=settings.sources_bucket,
            path=path,
            expires_in=settings.signed_url_expires_seconds,
        )
    prepared: list[dict[str, Any]] = []
    for row in rows:
        visual = row.get("visual") if isinstance(row.get("visual"), dict) else None
        path = storage_path_of(visual)
        prepared.append({**row, "visual": visual_for_response(visual, signed.get(path or ""))})
    return prepared


@router.get(
    "/workspaces/{workspace_id}/knowledge-titles",
    response_model=list[KnowledgeRunTitle],
)
async def list_knowledge_titles(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    projects: Annotated[KnowledgeProjectRepository, Depends(get_knowledge_project_repository)],
) -> list[KnowledgeRunTitle]:
    rows = await projects.list_titles(workspace.id)
    return [KnowledgeRunTitle.model_validate(row) for row in rows]


@router.get(
    "/workspaces/{workspace_id}/flashcards",
    response_model=list[FlashcardResponse],
)
async def list_flashcards(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FlashcardResponse]:
    rows = await assessments.list_flashcards(
        workspace.id,
        limit=limit,
        offset=offset,
    )
    signed = await _with_signed_visuals(rows, storage, settings)
    return [FlashcardResponse.model_validate(row) for row in signed]


@router.get("/flashcards/{flashcard_id}", response_model=FlashcardResponse)
async def get_flashcard(
    flashcard_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FlashcardResponse:
    row = await _readable_row(
        await assessments.get_flashcard_by_id(flashcard_id),
        user,
        workspaces,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard not found.",
        )

    signed = await _with_signed_visuals([row], storage, settings)
    return FlashcardResponse.model_validate(signed[0])


@router.get(
    "/workspaces/{workspace_id}/quizzes",
    response_model=list[QuizResponse],
)
async def list_quizzes(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[QuizResponse]:
    rows = await assessments.list_quizzes(
        workspace.id,
        limit=limit,
        offset=offset,
    )
    signed = await _with_signed_visuals(rows, storage, settings)
    return [QuizResponse.model_validate(row) for row in signed]


@router.get("/quizzes/{quiz_id}", response_model=QuizResponse)
async def get_quiz(
    quiz_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QuizResponse:
    row = await _readable_row(
        await assessments.get_quiz_by_id(quiz_id),
        user,
        workspaces,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz question not found.",
        )

    signed = await _with_signed_visuals([row], storage, settings)
    return QuizResponse.model_validate(signed[0])


@router.get(
    "/workspaces/{workspace_id}/scenarios",
    response_model=list[ScenarioResponse],
)
async def list_scenarios(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScenarioResponse]:
    rows = await assessments.list_scenarios(
        workspace.id,
        limit=limit,
        offset=offset,
    )
    signed = await _with_signed_visuals(rows, storage, settings)
    return [ScenarioResponse.model_validate(row) for row in signed]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScenarioResponse:
    row = await _readable_row(
        await assessments.get_scenario_by_id(scenario_id),
        user,
        workspaces,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    signed = await _with_signed_visuals([row], storage, settings)
    return ScenarioResponse.model_validate(signed[0])
