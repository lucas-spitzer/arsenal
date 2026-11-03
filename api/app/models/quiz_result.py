from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

QuizResultScope = Literal["one_per_term", "every_variant"]


class SubmittedQuizAnswer(BaseModel):
    quiz_id: str
    question: str = Field(min_length=1, max_length=4000)
    options: list[str] = Field(min_length=2, max_length=12)
    selected_index: int = Field(ge=0)


class QuizResultCreate(BaseModel):
    knowledge_project_id: str | None = None
    source_id: str | None = None
    scope: QuizResultScope
    answers: list[SubmittedQuizAnswer] = Field(min_length=1, max_length=200)


class QuizResultAnswer(BaseModel):
    quiz_id: str
    wiki_id: str | None
    question: str
    selected: str
    answer: str
    correct: bool


class QuizResultResponse(BaseModel):
    id: str
    workspace_id: str
    knowledge_project_id: str | None
    source_id: str | None
    title: str
    scope: QuizResultScope
    correct_count: int
    question_count: int
    answers: list[QuizResultAnswer]
    completed_at: datetime
