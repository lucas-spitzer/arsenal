import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.config import Settings, get_settings
from app.dependencies.auth import require_approved_user
from app.dependencies.services import get_atlas_service, get_supabase_storage_client
from app.dependencies.workspace import require_workspace
from app.models.atlas import (
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    AtlasAccessResponse,
    AtlasMeResponse,
    CompetitionSettingsResponse,
    CompetitionSettingsUpdate,
    DashboardResponse,
    ExamAttemptResponse,
    ExamQuestion,
    ExamStartRequest,
    LeaderboardResponse,
    PlatoonDashboardResponse,
    PracticeAnswerRequest,
)
from app.models.auth import CurrentUser
from app.models.workspace import WorkspaceResponse
from app.routers.assessments import with_signed_visuals
from app.services.atlas import AtlasError, AtlasService
from app.services.supabase_storage import SupabaseStorageClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workspaces/{workspace_id}/atlas", tags=["atlas"])

Storage = Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _raise(exc: AtlasError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def _with_question_images(
    attempt: ExamAttemptResponse,
    storage: SupabaseStorageClient,
    settings: Settings,
) -> ExamAttemptResponse:
    """Stored question images carry a storage path; the page needs a signed URL."""
    rows = [question.model_dump() for question in attempt.questions]
    if not any(row.get("visual") for row in rows):
        return attempt
    signed = await with_signed_visuals(rows, storage, settings)
    return attempt.model_copy(update={"questions": [ExamQuestion.model_validate(row) for row in signed]})


@router.post("/exams", response_model=ExamAttemptResponse, status_code=201)
async def start_exam(
    payload: ExamStartRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
    storage: Storage,
    settings: AppSettings,
) -> ExamAttemptResponse:
    try:
        attempt = await atlas.start_exam(
            user=user,
            workspace_id=workspace.id,
            owner_id=workspace.owner_id,
            payload=payload,
        )
    except AtlasError as exc:
        _raise(exc)
        raise
    return await _with_question_images(attempt, storage, settings)


@router.post("/exams/{attempt_id}/answers", response_model=AnswerSubmitResponse)
async def submit_exam_answer(
    attempt_id: str,
    payload: AnswerSubmitRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> AnswerSubmitResponse:
    started = time.perf_counter()
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
    finally:
        logger.debug("atlas answer graded in %.0f ms", (time.perf_counter() - started) * 1000)


@router.post("/exams/{attempt_id}/complete", response_model=ExamAttemptResponse)
async def complete_exam(
    attempt_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
    storage: Storage,
    settings: AppSettings,
) -> ExamAttemptResponse:
    try:
        attempt = await atlas.complete_exam(user=user, workspace_id=workspace.id, attempt_id=attempt_id)
    except AtlasError as exc:
        _raise(exc)
        raise
    return await _with_question_images(attempt, storage, settings)


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


@router.get("/dashboard", response_model=DashboardResponse)
async def atlas_dashboard(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
    user_id: str | None = None,
    subject_kind: str | None = None,
    subject_id: str | None = None,
    tz: str | None = None,
) -> DashboardResponse:
    try:
        return await atlas.dashboard(
            user=user,
            workspace_id=workspace.id,
            owner_id=workspace.owner_id,
            user_id=user_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            tz=tz,
        )
    except AtlasError as exc:
        _raise(exc)
        raise


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def leaderboard(
    response: Response,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    atlas: Annotated[AtlasService, Depends(get_atlas_service)],
) -> LeaderboardResponse:
    response.headers["Cache-Control"] = "no-store"
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
