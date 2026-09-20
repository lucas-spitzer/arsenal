from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AlignmentSource = Literal["provider", "forced", "estimated"]


@dataclass(frozen=True)
class WordTiming:
    index: int
    word: str
    start: float
    end: float
    start_char: int | None = None
    end_char: int | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "i": self.index,
            "w": self.word,
            "s": self.start,
            "e": self.end,
        }
        if self.start_char is not None and self.end_char is not None:
            value["cs"] = self.start_char
            value["ce"] = self.end_char
        return value


@dataclass(frozen=True)
class NarrationResult:
    audio: bytes
    words: list[WordTiming]
    duration_seconds: float
    request_id: str | None
    character_cost: int
    alignment_source: AlignmentSource = "provider"
    alignment_quality: dict[str, Any] = field(default_factory=dict)
