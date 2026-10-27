"""Academy ELO tab: TBS classes, their ELOs, and downloadable materials.

Not related to wiki_entries rows with entry_kind 'elo' (Knowledge runs).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

LessonResourceKind = Literal["file", "link"]
LessonIndexStatus = Literal["pending", "indexing", "ready", "failed", "skipped"]

MAX_OBJECTIVES = 100


def _required(value: str, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} is required.")
    return stripped


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _https_url(value: str) -> str:
    stripped = value.strip()
    if not stripped.lower().startswith("https://") or len(stripped) <= len("https://"):
        raise ValueError("Link must be an https:// URL.")
    if any(char.isspace() for char in stripped):
        raise ValueError("Link must not contain spaces.")
    return stripped


class LessonObjectiveInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    code: str | None = Field(default=None, max_length=40)
    is_async: bool = False

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return _required(value, "ELO text")

    @field_validator("code")
    @classmethod
    def _strip_code(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    sort_order: int | None = None
    notes: str | None = Field(default=None, max_length=2000)
    objectives: list[LessonObjectiveInput] = Field(default_factory=list, max_length=MAX_OBJECTIVES)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        return _required(value, "Title")

    @field_validator("notes")
    @classmethod
    def _strip_notes(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        return None if value is None else _required(value, "Title")

    @field_validator("notes")
    @classmethod
    def _strip_notes(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class LessonObjectivesReplace(BaseModel):
    objectives: list[LessonObjectiveInput] = Field(default_factory=list, max_length=MAX_OBJECTIVES)


class LessonLinkCreate(BaseModel):
    label: str = Field(default="MarineNet", max_length=200)
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        return value.strip() or "MarineNet"

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        return _https_url(value)


class LessonResourceUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    position: int | None = None

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str | None) -> str | None:
        return None if value is None else _required(value, "Label")

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        return None if value is None else _https_url(value)


class LessonObjectiveResponse(BaseModel):
    id: str
    lesson_id: str
    position: int
    text: str
    code: str | None = None
    is_async: bool = False


class LessonResourceResponse(BaseModel):
    id: str
    lesson_id: str
    kind: LessonResourceKind
    label: str
    position: int = 0
    url: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    index_status: LessonIndexStatus = "pending"
    index_error: str | None = None
    created_at: datetime
    updated_at: datetime


class LessonResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    sort_order: int = 0
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    objectives: list[LessonObjectiveResponse] = Field(default_factory=list)
    resources: list[LessonResourceResponse] = Field(default_factory=list)


class LessonDownloadResponse(BaseModel):
    url: str


class LessonReindexResponse(BaseModel):
    lessons: int
    files: int
