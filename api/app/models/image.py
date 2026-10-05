from pydantic import BaseModel, ConfigDict


class ImageCatalogModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    model: str
    provider: str
    display_name: str
    price_per_image: float | None = None
    capability_tier: int
    qualities: list[str] = []
    default_quality: str = "high"


class ImageCatalogResponse(BaseModel):
    models: list[ImageCatalogModelResponse]
