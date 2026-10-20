from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_admin, require_approved_user
from app.models.auth import CurrentUser
from app.models.tts import TtsCatalogModelResponse, TtsCatalogResponse, TtsVoiceResponse
from app.services.tts.catalog import TTS_MODEL_CATALOG

router = APIRouter(prefix="/tts", tags=["tts"], dependencies=[Depends(require_admin)])


@router.get("/catalog", response_model=TtsCatalogResponse)
async def get_tts_catalog(
    _: Annotated[CurrentUser, Depends(require_approved_user)],
) -> TtsCatalogResponse:
    return TtsCatalogResponse(
        models=[
            TtsCatalogModelResponse(
                model=entry.model,
                provider=entry.provider,
                display_name=entry.display_name,
                default_voice_id=entry.default_voice_id,
                voices=[
                    TtsVoiceResponse(id=voice.id, display_name=voice.display_name)
                    for voice in entry.voices
                ],
                price_per_million=entry.price_per_million,
                capability_tier=entry.capability_tier,
            )
            for entry in TTS_MODEL_CATALOG
        ],
    )
