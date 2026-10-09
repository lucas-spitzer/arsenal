from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
