from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GeneratedFlashcard(BaseModel):
    front: str
    back: str
    difficulty: str = "medium"
    tags: list[str] = Field(default_factory=list)
    wiki_ids_cited: list[str] = Field(default_factory=list)
    segment_ids_used: list[str] = Field(default_factory=list)


class FlashcardGenOutput(BaseModel):
    flashcards: list[GeneratedFlashcard]


class GeneratedQuizQuestion(BaseModel):
    question: str
    question_type: str = "multiple_choice"
    options: list[str] = Field(default_factory=list)
    correct_answer: str
    answer_pool: dict[str, Any] = Field(default_factory=dict)
    bloom_level: str | None = None
    explanation: str | None = None
    difficulty: str = "medium"
    wiki_ids_cited: list[str] = Field(default_factory=list)
    segment_ids_used: list[str] = Field(default_factory=list)


class QuizGenOutput(BaseModel):
    questions: list[GeneratedQuizQuestion]


class GeneratedScenario(BaseModel):
    title: str
    prompt: str
    context: str | None = None
    evaluation_criteria: list[str] = Field(default_factory=list)
    bloom_level: str | None = None
    difficulty: str = "medium"
    wiki_ids_cited: list[str] = Field(default_factory=list)
    segment_ids_used: list[str] = Field(default_factory=list)


class ScenarioGenOutput(BaseModel):
    scenarios: list[GeneratedScenario]
