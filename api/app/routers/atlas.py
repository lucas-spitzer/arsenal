from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import require_approved_user
from app.dependencies.services import get_atlas_service
from app.dependencies.workspace import require_workspace
from app.models.atlas import (
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    AtlasAccessResponse,
    AtlasMeResponse,
    CompetitionSettingsResponse,
    CompetitionSettingsUpdate,
    ExamAttemptResponse,
    ExamStartRequest,
    LeaderboardResponse,
    PlatoonDashboardResponse,
    PracticeAnswerRequest,
)
from app.models.auth import CurrentUser
from app.models.workspace import WorkspaceResponse
from app.services.atlas import AtlasError, AtlasService

router = APIRouter(prefix="/workspaces/{workspace_id}/atlas", tags=["atlas"])


def _raise(exc: AtlasError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/exams", response_model=ExamAttemptResponse, status_code=201)
async def start_exam(
    payload: ExamStartRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> ExamAttemptResponse:
    try:
        return await atlas.start_exam(
            user=user,
            workspace_id=workspace.id,
            owner_id=workspace.owner_id,
            payload=payload,
        )
    except AtlasError as exc:
        _raise(exc)
        raise


@router.post("/exams/{attempt_id}/answers", response_model=AnswerSubmitResponse)
async def submit_exam_answer(
    attempt_id: str,
    payload: AnswerSubmitRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> AnswerSubmitResponse:
    try:
        return await atlas.submit_exam_answer(
            user=user,
            workspace_id=workspace.id,
            attempt_id=attempt_id,
            payload=payload,
        )
    except AtlasError as exc:
        _raise(exc)
        raise


@router.post("/exams/{attempt_id}/complete", response_model=ExamAttemptResponse)
async def complete_exam(
    attempt_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> ExamAttemptResponse:
    try:
        return await atlas.complete_exam(user=user, workspace_id=workspace.id, attempt_id=attempt_id)
    except AtlasError as exc:
        _raise(exc)
        raise


@router.post("/practice/answers", response_model=AnswerSubmitResponse)
async def submit_practice_answer(
    payload: PracticeAnswerRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> AnswerSubmitResponse:
    try:
        return await atlas.submit_practice_answer(user=user, workspace_id=workspace.id, payload=payload)
    except AtlasError as exc:
        _raise(exc)
        raise


@router.get("/access", response_model=AtlasAccessResponse)
async def atlas_access(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> AtlasAccessResponse:
    return await atlas.access_status(workspace_id=workspace.id)


@router.get("/me", response_model=AtlasMeResponse)
async def atlas_me(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> AtlasMeResponse:
    try:
        return await atlas.me(user=user, workspace_id=workspace.id)
    except AtlasError as exc:
        _raise(exc)
        raise


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def leaderboard(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> LeaderboardResponse:
    try:
        return await atlas.leaderboard(user=user, workspace_id=workspace.id)
    except AtlasError as exc:
        _raise(exc)
        raise


@router.get("/competition", response_model=CompetitionSettingsResponse)
async def get_competition(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> CompetitionSettingsResponse:
    try:
        return await atlas.get_competition(user=user, workspace_id=workspace.id)
    except AtlasError as exc:
        _raise(exc)
        raise


@router.patch("/competition", response_model=CompetitionSettingsResponse)
async def update_competition(
    payload: CompetitionSettingsUpdate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> CompetitionSettingsResponse:
    try:
        return await atlas.update_competition(user=user, workspace_id=workspace.id, payload=payload)
    except AtlasError as exc:
        _raise(exc)
        raise


@router.post("/competition/finalize", response_model=CompetitionSettingsResponse)
async def finalize_competition(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> CompetitionSettingsResponse:
    try:
        return await atlas.finalize_competition(user=user, workspace_id=workspace.id)
    except AtlasError as exc:
        _raise(exc)
        raise


@router.get("/platoon", response_model=PlatoonDashboardResponse)
async def platoon_dashboard(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> PlatoonDashboardResponse:
    try:
        return await atlas.platoon_dashboard(user=user, workspace_id=workspace.id)
    except AtlasError as exc:
        _raise(exc)
        raise
