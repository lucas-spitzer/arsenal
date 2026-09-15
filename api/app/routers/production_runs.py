from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_production_run_repository,
    get_stage_run_repository,
    get_source_repository,
    get_wiki_ingest_batch_repository,
    get_workspace_repository,
)
from app.dependencies.workspace import require_workspace
from app.models.auth import CurrentUser
from app.models.production_run import ProductionRunCreate, ProductionRunResponse
from app.models.stage_run import StageRunResponse
from app.models.workspace import WorkspaceResponse
from app.pipeline import SUPPORTED_TARGET_ARTIFACTS
from app.repositories.production_runs import ProductionRunRepository
from app.repositories.stage_runs import StageRunRepository
from app.repositories.sources import SourceRepository
from app.repositories.wiki_ingest_batches import WikiIngestBatchRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.production_runs import (
    ProductionRunEnqueueError,
    ProductionRunValidationError,
    create_and_enqueue_production_run,
)
from app.services.stage_run_backfill import enrich_stage_run_row

router = APIRouter(tags=["production-runs"])


def _validate_target_artifacts(target_artifacts: list[str]) -> None:
    unknown = [
        artifact
        for artifact in target_artifacts
        if artifact not in SUPPORTED_TARGET_ARTIFACTS
    ]

    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported target artifacts: {', '.join(unknown)}",
        )


@router.get(
    "/workspaces/{workspace_id}/production-runs",
    response_model=list[ProductionRunResponse],
)
async def list_production_runs(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    production_runs: Annotated[
        ProductionRunRepository,
        Depends(get_production_run_repository),
    ],
) -> list[ProductionRunResponse]:
    rows = await production_runs.list_for_workspace(workspace.id, user.id)
    return [ProductionRunResponse.model_validate(row) for row in rows]


@router.post(
    "/workspaces/{workspace_id}/production-runs",
    response_model=ProductionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_production_run(
    payload: ProductionRunCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    sources: Annotated[SourceRepository, Depends(get_source_repository)],
    batches: Annotated[WikiIngestBatchRepository, Depends(get_wiki_ingest_batch_repository)],
    production_runs: Annotated[
        ProductionRunRepository,
        Depends(get_production_run_repository),
    ],
) -> ProductionRunResponse:
    _validate_target_artifacts(payload.target_artifacts)

    found_sources = await sources.get_many_for_workspace(
        payload.source_ids,
        workspace.id,
        user.id,
    )

    if len(found_sources) != len(set(payload.source_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more source_ids are invalid for this workspace.",
        )

    try:
        row = await create_and_enqueue_production_run(
            workspace_id=workspace.id,
            owner_id=user.id,
            source_ids=payload.source_ids,
            target_artifacts=payload.target_artifacts,
            settings=settings,
            production_runs=production_runs,
            sources=found_sources,
            batches=batches,
        )
    except ProductionRunValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ProductionRunEnqueueError:
        raise

    return ProductionRunResponse.model_validate(row)


@router.get("/production-runs/{production_run_id}", response_model=ProductionRunResponse)
async def get_production_run(
    production_run_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    production_runs: Annotated[
        ProductionRunRepository,
        Depends(get_production_run_repository),
    ],
) -> ProductionRunResponse:
    row = await production_runs.get_for_owner(production_run_id, user.id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Production run not found.",
        )

    return ProductionRunResponse.model_validate(row)


@router.get(
    "/production-runs/{production_run_id}/stage-runs",
    response_model=list[StageRunResponse],
)
async def list_production_run_stage_runs(
    production_run_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    production_runs: Annotated[
        ProductionRunRepository,
        Depends(get_production_run_repository),
    ],
    stage_runs: Annotated[StageRunRepository, Depends(get_stage_run_repository)],
) -> list[StageRunResponse]:
    production_run = await production_runs.get_for_owner(production_run_id, user.id)

    if not production_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Production run not found.",
        )

    rows = await stage_runs.list_for_production_run(production_run_id)
    return [StageRunResponse.model_validate(enrich_stage_run_row(row)) for row in rows]


@router.get("/stage-runs/{stage_run_id}", response_model=StageRunResponse)
async def get_stage_run(
    stage_run_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    stage_runs: Annotated[StageRunRepository, Depends(get_stage_run_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> StageRunResponse:
    row = await stage_runs.get(stage_run_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stage run not found.",
        )

    workspace = await workspaces.get_for_owner(row["workspace_id"], user.id)

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stage run not found.",
        )

    return StageRunResponse.model_validate(enrich_stage_run_row(row))
