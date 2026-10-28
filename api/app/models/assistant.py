from typing import Any, Literal

from pydantic import BaseModel, Field

AssistantMode = Literal["discussion", "scenario"]
DiscussionSubmode = Literal["socratic", "euclidean", "tbs"]


class AssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantChatRequest(BaseModel):
    mode: AssistantMode
    submode: DiscussionSubmode | None = None
    messages: list[AssistantMessage] = Field(default_factory=list)
    # Optional narrowing: restrict retrieval to specific source documents.
    source_ids: list[str] | None = None
    # Optional focus on Academy ELO classes. Lesson material is searched either way.
    lesson_ids: list[str] | None = None
    # Required when mode == "scenario" to load its evaluation_criteria/rubric.
    scenario_id: str | None = None


class Citation(BaseModel):
    kind: Literal["segment", "wiki", "lesson"]
    label: str
    snippet: str
    similarity: float
    reader_link: str | None = None
    locator: dict[str, Any] = Field(default_factory=dict)


class ScenarioEvaluation(BaseModel):
    passed: bool
    score: float | None = None
    feedback: str
    met_criteria: list[str] = Field(default_factory=list)
    missed_criteria: list[str] = Field(default_factory=list)


class AssistantChatResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[Citation] = Field(default_factory=list)
    evaluation: ScenarioEvaluation | None = None


# --- Persisted discussion threads ------------------------------------------


class EloCheck(BaseModel):
    """Private rubric for an ELO discussion. Never persisted on a message."""

    question: str
    answer: str


class DiscussionThreadResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    submode: DiscussionSubmode
    source_id: str | None = None
    lesson_id: str | None = None
    wiki_entry_id: str | None = None
    created_at: str
    updated_at: str


class DiscussionMessageResponse(BaseModel):
    id: str
    thread_id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: str


class DiscussionThreadDetailResponse(DiscussionThreadResponse):
    messages: list[DiscussionMessageResponse] = Field(default_factory=list)


class CreateDiscussionThreadRequest(BaseModel):
    title: str
    submode: DiscussionSubmode = "tbs"
    source_id: str | None = None
    lesson_id: str | None = None
    # Canonical ELO whose question opens the thread. The stored definition stays server-side.
    wiki_entry_id: str | None = None
    # Optional assistant-authored opener persisted as the first message.
    seed_prompt: str | None = None


class UpdateDiscussionThreadRequest(BaseModel):
    title: str | None = None
    submode: DiscussionSubmode | None = None


class SendDiscussionMessageRequest(BaseModel):
    content: str


class SendDiscussionMessageResponse(BaseModel):
    user_message: DiscussionMessageResponse
    assistant_message: DiscussionMessageResponse
    grounded: bool
