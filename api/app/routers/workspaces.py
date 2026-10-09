from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.artifact_paths import next_available_slug, storage_slug
from app.config import get_settings
from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_stage_settings_repository,
    get_workspace_repository,
)
from app.dependencies.workspace import require_workspace
from app.errors import is_duplicate_key_error
from app.image_defaults import (
    STUDY_MATERIAL_IMAGE_ACTION,
    STUDY_MATERIAL_IMAGE_LABEL,
)
from app.llm_actions import LLM_ACTIONS
from app.mathesys.study_material.images import (
    effective_stage_image_quality,
    normalize_stage_image_quality,
    stage_image_options,
)
from app.models.auth import CurrentUser
from app.models.stage_settings import (
    StageSetting,
    StageSettingsResponse,
    StageSettingUpdate,
)
from app.models.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate
from app.repositories.stage_settings import StageSettingsRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.images.catalog import validate_image_selection
from app.services.llm.model_catalog import validate_selection
from app.services.supabase_rest import SupabaseRestError
from app.services.tts.catalog import validate_tts_selection
from app.tts_defaults import (
    AUDIO_NARRATION_ACTION,
    AUDIO_NARRATION_LABEL,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

_STAGE_ACTION_LABELS: dict[str, str] = {
    **{action.key: action.label for action in LLM_ACTIONS},
    AUDIO_NARRATION_ACTION: AUDIO_NARRATION_LABEL,
    STUDY_MATERIAL_IMAGE_ACTION: STUDY_MATERIAL_IMAGE_LABEL,
}


def _default_provider_model(stage_action: str) -> tuple[str, str]:
    if stage_action == AUDIO_NARRATION_ACTION:
        narration = get_settings().narration
        return narration.provider, narration.model_id
    if stage_action == STUDY_MATERIAL_IMAGE_ACTION:
        study = get_settings().study_material
        if study.image_provider == "google":
            model = study.google_image_model
        elif study.image_provider == "xai":
            model = study.xai_image_model
        else:
            model = study.openai_image_model
        return study.image_provider, model
    resolved = get_settings().llm.resolve_action(stage_action)
    return resolved.provider, resolved.model


def _default_voice_id(stage_action: str) -> str | None:
    if stage_action == AUDIO_NARRATION_ACTION:
        return get_settings().narration.voice_id
    return None


def _image_controls(
    stage_action: str,
    provider: str,
    model: str,
    row: dict[str, object] | None,
    default_provider: str,
    default_model: str,
) -> tuple[str | None, str | None]:
    if stage_action != STUDY_MATERIAL_IMAGE_ACTION:
        return None, None
    _, default_quality = stage_image_options(default_provider, default_model)
    stored_quality = str(row.get("image_quality") or "") if row else None
    quality = effective_stage_image_quality(provider, model, stored_quality)
    return quality, default_quality


def _setting_from_row(
    *,
    stage_action: str,
    row: dict[str, object] | None,
) -> StageSetting:
    default_provider, default_model = _default_provider_model(stage_action)
    default_voice = _default_voice_id(stage_action)
    provider = str(row["provider"]) if row else default_provider
    model = str(row["model"]) if row else default_model
    image_quality, default_image_quality = _image_controls(
        stage_action,
        provider,
        model,
        row,
        default_provider,
        default_model,
    )
    return StageSetting(
        stage_action=stage_action,
        label=_STAGE_ACTION_LABELS[stage_action],
        provider=provider,
        model=model,
        reasoning_effort=row.get("reasoning_effort") if row else None,
        reasoning_tokens=row.get("reasoning_tokens") if row else None,
        voice_id=(str(row["voice_id"]) if row and row.get("voice_id") else default_voice),
        image_quality=image_quality,
        is_overridden=row is not None,
        default_provider=default_provider,
        default_model=default_model,
        default_voice_id=default_voice,
        default_image_quality=default_image_quality,
    )


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> list[WorkspaceResponse]:
    rows = await workspaces.list_for_owner(user.id)
    return [WorkspaceResponse.model_validate(row) for row in rows]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceResponse:
    taken = await workspaces.list_slugs()
    slug = next_available_slug(storage_slug(payload.name, fallback="workspace"), taken)
    try:
        row = await workspaces.create(
            owner_id=user.id,
            name=payload.name,
            slug=slug,
            description=payload.description,
        )
    except SupabaseRestError as exc:
        if is_duplicate_key_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A workspace with this name already exists.",
            ) from exc
        raise
    return WorkspaceResponse.model_validate(row)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
) -> WorkspaceResponse:
    return workspace


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    payload: WorkspaceUpdate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceResponse:
    updates = payload.model_dump(exclude_unset=True)

    updates.pop("slug", None)

    if not updates:
        return workspace

    try:
        row = await workspaces.update(workspace.id, user.id, updates)
    except SupabaseRestError as exc:
        if is_duplicate_key_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A workspace with this name already exists.",
            ) from exc
        raise

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    return WorkspaceResponse.model_validate(row)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> None:
    await workspaces.delete(workspace.id, user.id)


@router.get("/{workspace_id}/stage-settings", response_model=StageSettingsResponse)
async def get_stage_settings(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    stage_settings: Annotated[
        StageSettingsRepository,
        Depends(get_stage_settings_repository),
    ],
) -> StageSettingsResponse:
    stored = {
        str(row["stage_action"]): row
        for row in await stage_settings.list_for_workspace(workspace.id)
    }

    settings: list[StageSetting] = []
    for action in LLM_ACTIONS:
        settings.append(
            _setting_from_row(stage_action=action.key, row=stored.get(action.key)),
        )
    settings.append(
        _setting_from_row(
            stage_action=AUDIO_NARRATION_ACTION,
            row=stored.get(AUDIO_NARRATION_ACTION),
        ),
    )
    settings.append(
        _setting_from_row(
            stage_action=STUDY_MATERIAL_IMAGE_ACTION,
            row=stored.get(STUDY_MATERIAL_IMAGE_ACTION),
        ),
    )

    return StageSettingsResponse(settings=settings)


@router.put("/{workspace_id}/stage-settings/{stage_action}", response_model=StageSetting)
async def put_stage_setting(
    stage_action: str,
    payload: StageSettingUpdate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    stage_settings: Annotated[
        StageSettingsRepository,
        Depends(get_stage_settings_repository),
    ],
) -> StageSetting:
    if stage_action not in _STAGE_ACTION_LABELS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown stage action '{stage_action}'.",
        )

    if stage_action == AUDIO_NARRATION_ACTION:
        error = validate_tts_selection(payload.provider, payload.model)
    elif stage_action == STUDY_MATERIAL_IMAGE_ACTION:
        error = validate_image_selection(payload.provider, payload.model)
    else:
        error = validate_selection(payload.provider, payload.model)
    if error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error,
        )

    provider = payload.provider.strip().lower()
    model = payload.model.strip()
    reasoning_effort = payload.reasoning_effort.strip().lower() if payload.reasoning_effort else None
    voice_id = payload.voice_id.strip() if payload.voice_id else None
    image_quality: str | None = None
    if stage_action == AUDIO_NARRATION_ACTION:
        if not voice_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Voice ID is required for audio narration.",
            )
        reasoning_effort = None
        reasoning_tokens = None
    elif stage_action == STUDY_MATERIAL_IMAGE_ACTION:
        reasoning_effort = None
        reasoning_tokens = None
        voice_id = None
        image_quality = normalize_stage_image_quality(provider, model, payload.image_quality)
        if image_quality is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Quality '{payload.image_quality}' is not available for this image model.",
            )
    else:
        reasoning_tokens = payload.reasoning_tokens
        voice_id = None

    row = await stage_settings.upsert(
        workspace_id=workspace.id,
        stage_action=stage_action,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort or None,
        reasoning_tokens=reasoning_tokens,
        voice_id=voice_id,
        image_quality=image_quality,
    )

    return _setting_from_row(stage_action=stage_action, row=row)


@router.delete(
    "/{workspace_id}/stage-settings/{stage_action}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_stage_setting(
    stage_action: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    stage_settings: Annotated[
        StageSettingsRepository,
        Depends(get_stage_settings_repository),
    ],
) -> None:
    if stage_action not in _STAGE_ACTION_LABELS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown stage action '{stage_action}'.",
        )

    await stage_settings.delete(workspace_id=workspace.id, stage_action=stage_action)
