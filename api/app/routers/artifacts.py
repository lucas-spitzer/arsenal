from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.config import Settings, get_settings
from app.access import can_read_library
from app.dependencies.auth import require_admin, require_approved_user
from app.dependencies.services import (
    get_artifact_repository,
    get_assessment_repository,
    get_source_repository,
    get_supabase_storage_client,
    get_wiki_entry_repository,
    get_workspace_repository,
)
from app.dependencies.workspace import require_workspace
from app.models.artifact import (
    ArtifactDownloadResponse,
    ArtifactResponse,
    LibraryArtifactUploadResponse,
)
from app.models.auth import CurrentUser
from app.models.workspace import WorkspaceResponse
from app.repositories.artifacts import ArtifactRepository
from app.repositories.assessments import AssessmentRepository
from app.repositories.sources import SourceRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.library_artifacts import LibraryArtifactError, upload_library_artifact
from app.services.narration_combine import (
    narration_download_filename,
    narration_download_state,
)
from app.services.queue import enqueue_narration_combine
from app.services.supabase_storage import SupabaseStorageClient, SupabaseStorageError

router = APIRouter(tags=["artifacts"])


async def _readable_artifact(
    artifact_id: str,
    user: CurrentUser,
    artifacts: ArtifactRepository,
    workspaces: WorkspaceRepository,
) -> dict[str, Any] | None:
    row = await artifacts.get(artifact_id)
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


@router.get(
    "/workspaces/{workspace_id}/artifacts",
    response_model=list[ArtifactResponse],
)
async def list_artifacts(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    artifact_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ArtifactResponse]:
    rows = await artifacts.list_for_workspace(
        workspace.id,
        artifact_type=artifact_type,
        limit=limit,
        offset=offset,
    )
    return [ArtifactResponse.model_validate(row) for row in rows]


@router.post(
    "/workspaces/{workspace_id}/library-artifacts",
    response_model=LibraryArtifactUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_workspace_library_artifact(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    sources: Annotated[SourceRepository, Depends(get_source_repository)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    source_id: Annotated[str, Form()],
    artifact_type: Annotated[str, Form()],
    title: Annotated[str, Form()],
    file: UploadFile = File(...),
) -> LibraryArtifactUploadResponse:
    """Attach one audiobook MP3 or knowledge JSON file to an existing source."""
    source = await sources.get_for_workspace(source_id, workspace.id, user.id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    content = await file.read()
    try:
        result = await upload_library_artifact(
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            source=source,
            artifact_type=artifact_type,
            title=title,
            filename=file.filename,
            content=content,
            json_max_bytes=settings.max_source_upload_bytes,
            bucket=settings.sources_bucket,
            artifacts=artifacts,
            wiki_entries=wiki_entries,
            assessments=assessments,
            storage=storage,
        )
    except LibraryArtifactError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SupabaseStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not store the audiobook file.",
        ) from exc
    return LibraryArtifactUploadResponse.model_validate(result)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> ArtifactResponse:
    row = await _readable_artifact(artifact_id, user, artifacts, workspaces)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found.",
        )

    return ArtifactResponse.model_validate(row)


@router.get("/artifacts/{artifact_id}/download", response_model=ArtifactDownloadResponse)
async def download_artifact(
    artifact_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
) -> ArtifactDownloadResponse:
    row = await _readable_artifact(artifact_id, user, artifacts, workspaces)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found.",
        )

    if row.get("artifact_type") == "narration_audio":
        return await _narration_download(
            artifact_id,
            row,
            settings=settings,
            artifacts=artifacts,
            storage=storage,
        )

    download_url = await storage.create_signed_url(
        bucket=settings.sources_bucket,
        path=row["storage_path"],
        expires_in=settings.signed_url_expires_seconds,
    )

    return ArtifactDownloadResponse(
        artifact_id=artifact_id,
        filename=row["filename"],
        download_url=download_url,
        expires_in=settings.signed_url_expires_seconds,
        status="ready",
    )


async def _narration_download(
    artifact_id: str,
    row: dict[str, Any],
    *,
    settings: Settings,
    artifacts: ArtifactRepository,
    storage: SupabaseStorageClient,
) -> ArtifactDownloadResponse:
    manifest = row.get("manifest") or {}
    if not isinstance(manifest, dict):
        manifest = {}
    if str(manifest.get("status") or "") == "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Narration is still being generated.",
        )

    state = narration_download_state(manifest)
    filename = narration_download_filename(manifest)
    if state == "ready":
        download_url = await storage.create_signed_url(
            bucket=settings.sources_bucket,
            path=str(manifest["combined_audio_path"]),
            expires_in=settings.signed_url_expires_seconds,
            download_name=filename,
        )
        return ArtifactDownloadResponse(
            artifact_id=artifact_id,
            filename=filename,
            download_url=download_url,
            expires_in=settings.signed_url_expires_seconds,
            status="ready",
        )

    if state == "missing":
        updated = dict(manifest)
        updated["combined_audio_status"] = "preparing"
        updated.pop("combined_audio_path", None)
        updated.pop("combined_audio_error", None)
        await artifacts.update(artifact_id, {"manifest": updated})
        try:
            enqueue_narration_combine(settings, artifact_id)
        except Exception as exc:
            updated["combined_audio_status"] = "failed"
            updated["combined_audio_error"] = str(exc)
            await artifacts.update(artifact_id, {"manifest": updated})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not start preparing the audio file.",
            ) from exc

    return ArtifactDownloadResponse(
        artifact_id=artifact_id,
        filename=filename,
        download_url=None,
        expires_in=settings.signed_url_expires_seconds,
        status="preparing",
    )
