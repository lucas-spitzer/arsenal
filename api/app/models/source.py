from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReferenceSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    background: str | None = Field(default=None, max_length=4000)
    document_type: str | None = Field(default=None, max_length=200)
    issuing_authority: str | None = Field(default=None, max_length=200)


class SourceResponse(BaseModel):
    id: str
    workspace_id: str
    owner_id: str
    filename: str
    slug: str
    mime_type: str
    storage_path: str
    file_hash: str
    file_size_bytes: int
    source_metadata: dict[str, Any]
    status: str
    source_kind: str = "document"
    created_at: datetime
    updated_at: datetime
