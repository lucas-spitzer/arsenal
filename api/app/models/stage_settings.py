from pydantic import BaseModel, ConfigDict, Field


class StageSettingUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reasoning_effort: str | None = Field(default=None, max_length=50)
    reasoning_tokens: int | None = Field(default=None, gt=0)
    voice_id: str | None = Field(default=None, max_length=200)
    image_quality: str | None = Field(default=None, max_length=50)


class StageSetting(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    stage_action: str
    label: str
    provider: str
    model: str
    reasoning_effort: str | None = None
    reasoning_tokens: int | None = None
    voice_id: str | None = None
    image_quality: str | None = None
    is_overridden: bool
    default_provider: str
    default_model: str
    default_voice_id: str | None = None
    default_image_quality: str | None = None


class StageSettingsResponse(BaseModel):
    settings: list[StageSetting]
