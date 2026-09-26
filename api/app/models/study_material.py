from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ComponentType = Literal["text", "diagram", "image"]


class StudyMaterialOptions(BaseModel):
    logo_locked: bool = False
    logo_id: str | None = None
    footer_text: str = Field(default="", max_length=400)
    section_notes: dict[str, str] = Field(default_factory=dict)


class StudyMaterialCreate(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    theme_id: str = Field(min_length=1, max_length=80)
    template_id: str = Field(min_length=1, max_length=80)
    options: StudyMaterialOptions = Field(default_factory=StudyMaterialOptions)


class StudyMaterialUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=140)
    options: StudyMaterialOptions | None = None


class ComponentCreate(BaseModel):
    section_id: str = Field(min_length=1, max_length=80)
    component_type: ComponentType
    instructions: str = Field(default="", max_length=8000)
    settings: dict[str, Any] = Field(default_factory=dict)


class ComponentUpdate(BaseModel):
    instructions: str | None = Field(default=None, max_length=8000)
    settings: dict[str, Any] | None = None


class ComponentFileResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    file_size_bytes: int


class ComponentVersionResponse(BaseModel):
    id: str
    version: int
    output: dict[str, Any]
    output_path: str | None
    instructions: str
    model: str | None
    provider: str | None
    settings: dict[str, Any]
    theme_id: str
    created_at: datetime


class StudyMaterialComponentResponse(BaseModel):
    id: str
    section_id: str
    component_type: ComponentType
    position: int
    instructions: str
    settings: dict[str, Any]
    files: list[ComponentFileResponse]
    active_version_id: str | None
    active_version: ComponentVersionResponse | None = None
    version_count: int = 0
    created_at: datetime
    updated_at: datetime


class StudyMaterialResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    slug: str
    theme_id: str
    template_id: str
    options: dict[str, Any]
    status: str
    layout: dict[str, Any]
    validation: dict[str, Any]
    production_run_id: str | None
    artifact_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    component_count: int = 0
    components: list[StudyMaterialComponentResponse] = Field(default_factory=list)
