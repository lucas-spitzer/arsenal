from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CalendarEventKind = Literal["deadline", "class", "prac_app", "evaluation"]


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def times_in_order(start_time: time | None, end_time: time | None) -> bool:
    return start_time is None or end_time is None or end_time >= start_time


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: CalendarEventKind = "class"
    event_date: date
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title is required.")
        return stripped

    @field_validator("location", "notes")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _check_times(self) -> "CalendarEventCreate":
        if not times_in_order(self.start_time, self.end_time):
            raise ValueError("End time must be at or after start time.")
        return self


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    kind: CalendarEventKind | None = None
    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title is required.")
        return stripped

    @field_validator("location", "notes")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class CalendarEventResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    kind: CalendarEventKind
    event_date: date
    start_time: time | None
    end_time: time | None
    location: str | None
    notes: str | None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
