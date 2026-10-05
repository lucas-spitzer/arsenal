from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_approved_user
from app.models.auth import CurrentUser
from app.mathesys.study_material.images import stage_image_options
from app.models.image import ImageCatalogModelResponse, ImageCatalogResponse
from app.services.images.catalog import IMAGE_MODEL_CATALOG

router = APIRouter(prefix="/image", tags=["image"])


@router.get("/catalog", response_model=ImageCatalogResponse)
async def get_image_catalog(
    _: Annotated[CurrentUser, Depends(require_approved_user)],
) -> ImageCatalogResponse:
    models: list[ImageCatalogModelResponse] = []
    for entry in IMAGE_MODEL_CATALOG:
        qualities, default_quality = stage_image_options(entry.provider, entry.model)
        models.append(
            ImageCatalogModelResponse(
                model=entry.model,
                provider=entry.provider,
                display_name=entry.display_name,
                price_per_image=entry.price_per_image,
                capability_tier=entry.capability_tier,
                qualities=list(qualities),
                default_quality=default_quality,
            ),
        )
    return ImageCatalogResponse(models=models)
