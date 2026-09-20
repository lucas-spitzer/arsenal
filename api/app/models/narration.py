from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NarrationSegmentResponse(BaseModel):
    id: str
    source_id: str
    workspace_id: str
    chapter_id: str | None = None
    segment_id: str
    provider: str
    voice_id: str
    model_id: str
    text_hash: str
    duration_seconds: float
    audio_path: str | None = None
    # Word timings [{i, w, s, e}] — word index, word, start/end seconds
    # on the shared chapter (or chapter-split) audio clip.
    words: list[dict[str, Any]]
    alignment_source: str = "provider"
    alignment_quality: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class NarrationAudioResponse(BaseModel):
    narration_id: str
    segment_id: str
    audio_url: str
    expires_in: int
