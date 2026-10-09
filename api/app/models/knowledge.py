from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class KnowledgeProjectSummary(BaseModel):
    id: str
    workspace_id: str
    source_id: str
    title: str
    status: str
    error: str | None = None
    notes_filename: str | None = None
    draft_questions: bool = False
    draft_scenarios: bool = False
    batch_instructions: dict[str, str] = Field(default_factory=dict)
    structure_run_id: str | None = None
    draft_run_id: str | None = None
    visual_run_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AssessmentVisualResponse(BaseModel):
    kind: str
    placement: str
    alt: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    url: str | None = None


class AnswerPoolDistractor(BaseModel):
    text: str
    misconception: str = ""
    confused_with_wiki_id: str | None = None


class AnswerPoolPayload(BaseModel):
    correct: list[str] = Field(default_factory=list)
    distractors: list[AnswerPoolDistractor] = Field(default_factory=list)
    show_count: int = 4


class KnowledgeFlashcardView(BaseModel):
    assessment_id: str
    front: str
    back: str


class KnowledgeQuestionView(BaseModel):
    plan_id: str
    assessment_id: str
    question: str
    subtype: str
    question_type: str
    options: list[Any] = Field(default_factory=list)
    correct_answer: str
    answer_pool: dict[str, Any] = Field(default_factory=dict)
    bloom_level: str | None = None
    explanation: str | None = None
    difficulty: str = "medium"
    draft: dict[str, Any] | None = None


class KnowledgeScenarioView(BaseModel):
    plan_id: str
    assessment_id: str
    title: str
    prompt: str
    context: str | None = None
    evaluation_criteria: list[Any] = Field(default_factory=list)
    subtype: str
    bloom_level: str | None = None
    difficulty: str = "medium"
    draft: dict[str, Any] | None = None


class KnowledgeEntryView(BaseModel):
    wiki_entry_id: str
    preferred_label: str
    definition: str
    significance: str | None = None
    category: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    entry_kind: str
    importance: str
    plan_id: str
    enabled: bool
    layout: str = "label_description"
    instructions: str = ""
    visual: AssessmentVisualResponse | None = None
    flashcard: KnowledgeFlashcardView | None = None
    questions: list[KnowledgeQuestionView] = Field(default_factory=list)
    scenarios: list[KnowledgeScenarioView] = Field(default_factory=list)


class KnowledgeDraftItem(BaseModel):
    plan_id: str
    item_type: str
    assessment_id: str | None = None
    title: str
    body: str
    visual: AssessmentVisualResponse | None = None


class KnowledgeProjectDetail(KnowledgeProjectSummary):
    pipeline: list[dict[str, Any]] = Field(default_factory=list)
    entries: list[KnowledgeEntryView] = Field(default_factory=list)
    items: list[KnowledgeDraftItem] = Field(default_factory=list)


class KnowledgeProjectUpdate(BaseModel):
    draft_questions: bool | None = None
    draft_scenarios: bool | None = None
    batch_instructions: dict[str, str] | None = None


class KnowledgePlanUpdate(BaseModel):
    enabled: bool | None = None
    layout: str | None = None
    instructions: str | None = None
    draft: dict[str, Any] | None = None
    clear_draft: bool = False


class KnowledgeBatchRequest(BaseModel):
    kind: Literal["question", "scenario"]
    category: str
    format: str
    instructions: str = ""
    per_entry: int = Field(default=1, ge=1, le=3)
    bloom_level: str = ""
    mode: Literal["append", "replace"] = "append"


class KnowledgeVariantsRequest(BaseModel):
    kind: Literal["question", "scenario"]
    wiki_entry_id: str
    format: str
    count: int = Field(default=1, ge=1, le=5)
    mix: Literal["same", "spread"] = "same"
    bloom_level: str = ""
    instructions: str = ""


class KnowledgeQuestionSave(BaseModel):
    question: str
    format: str
    answer_pool: AnswerPoolPayload
    explanation: str | None = None
    difficulty: str = "medium"
    bloom_level: str | None = None


class KnowledgeScenarioSave(BaseModel):
    title: str
    prompt: str
    context: str | None = None
    evaluation_criteria: list[str] = Field(default_factory=list)
    format: str
    difficulty: str = "medium"
    bloom_level: str | None = None


class KnowledgeFlashcardSave(BaseModel):
    front: str
    back: str
