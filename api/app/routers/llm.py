from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_admin, require_approved_user
from app.models.auth import CurrentUser
from app.models.llm import ModelCatalogResponse, build_model_catalog_response

router = APIRouter(prefix="/llm", tags=["llm"], dependencies=[Depends(require_admin)])


@router.get("/catalog", response_model=ModelCatalogResponse)
async def get_model_catalog(
    _: Annotated[CurrentUser, Depends(require_approved_user)],
) -> ModelCatalogResponse:
    return build_model_catalog_response()
