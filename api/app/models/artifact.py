from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ArtifactResponse(BaseModel):
    id: str
    workspace_id: str
    source_id: str | None
    production_run_id: str | None
    artifact_type: str
    format: str
    filename: str
    storage_path: str
    file_size_bytes: int
    manifest: dict[str, Any]
    origin: dict[str, Any]
    created_at: datetime


class LibraryArtifactUploadResponse(BaseModel):
    artifact_type: Literal["audiobook", "knowledge"]
    source_id: str
    title: str
    artifact: ArtifactResponse | None = None
    wiki_entry_count: int = 0
    question_count: int = 0


class ArtifactDownloadResponse(BaseModel):
    artifact_id: str
    filename: str
    download_url: str | None = None
    expires_in: int
    status: Literal["ready", "preparing"] = "ready"
