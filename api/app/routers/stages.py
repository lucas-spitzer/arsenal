from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import require_admin, require_approved_user
from app.dependencies.services import get_stage_repository
from app.models.auth import CurrentUser
from app.models.stage import StageResponse
from app.repositories.stages import StageRepository

router = APIRouter(prefix="/stages", tags=["stages"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[StageResponse])
async def list_stages(
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    stages: Annotated[StageRepository, Depends(get_stage_repository)],
    module: Annotated[str | None, Query(pattern="^(intellex|mathesys|qngen)$")] = None,
) -> list[StageResponse]:
    rows = await stages.list_active(module=module)
    return [StageResponse.model_validate(row) for row in rows]


@router.get("/{stage_id}/{version}", response_model=StageResponse)
async def get_stage(
    stage_id: str,
    version: str,
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    stages: Annotated[StageRepository, Depends(get_stage_repository)],
) -> StageResponse:
    row = await stages.get(stage_id, version)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stage not found.",
        )

    return StageResponse.model_validate(row)
