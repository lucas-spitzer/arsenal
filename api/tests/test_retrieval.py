from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.models.assistant import AssistantChatRequest, AssistantChatResponse, SendDiscussionMessageRequest
from app.models.auth import CurrentUser
from app.models.workspace import WorkspaceResponse
from app.routers.assistant import send_discussion_message
from app.services.retrieval import RetrievalService


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.5] for _ in texts]


class FakeRepo:
    def __init__(self) -> None:
        self.lesson_calls: list[dict[str, Any]] = []
        self.segment_calls: list[dict[str, Any]] = []

    async def match_segments(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.segment_calls.append(kwargs)
        return [
            {
                "source_id": "src-1",
                "sequence_index": 4,
                "text": "Book passage",
                "chapter_title": "Chapter 1",
                "locator": {"page": 9},
                "similarity": 0.61,
            }
        ]

    async def match_wiki_entries(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": "w1", "preferred_label": "OODA", "canonical_slug": "ooda", "definition": "Loop", "similarity": 0.5}]

    async def match_lesson_chunks(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.lesson_calls.append(kwargs)
        return [
            {
                "lesson_id": "lesson-1",
                "resource_id": None,
                "objective_id": "o3",
                "kind": "objective",
                "sequence_index": 3,
                "text": "Decision Making — ELO 3: Define analytical decision-making.",
                "locator": {"position": 3, "code": "MCS-CMBH-1002c"},
                "lesson_title": "Decision Making",
                "resource_label": None,
                "filename": None,
                "similarity": 0.8,
            },
            {
                "lesson_id": "lesson-1",
                "resource_id": "res-9",
                "objective_id": None,
                "kind": "file_text",
                "sequence_index": 0,
                "text": "Decision Making · OODA.pptx · slide 4\nObserve...",
                "locator": {"slide": 4},
                "lesson_title": "Decision Making",
                "resource_label": "OODA.pptx",
                "filename": "OODA.pptx",
                "similarity": 0.55,
            },
        ]


def _service(repo: FakeRepo) -> RetrievalService:
    return RetrievalService(repo, embedding_client=FakeEmbedder(), lesson_count=6)  # type: ignore[arg-type]


def test_lesson_chunks_are_merged_and_sorted() -> None:
    repo = FakeRepo()

    chunks = asyncio.run(_service(repo).retrieve("what is analytical decision making", "ws-1"))

    assert [chunk.kind for chunk in chunks] == ["lesson", "segment", "lesson", "wiki"]
    assert chunks[0].label == "Decision Making · ELO 3 (MCS-CMBH-1002c)"
    assert chunks[0].reader_link == "/app/elo/lesson-1"
    assert chunks[2].label == "Decision Making · OODA.pptx · slide 4"
    assert chunks[2].reader_link == "/app/elo/lesson-1?resource=res-9"
    assert chunks[2].locator["slide"] == 4
    assert chunks[0].to_citation()["kind"] == "lesson"


def test_lesson_chunks_still_searched_when_scoped_to_a_book() -> None:
    repo = FakeRepo()

    asyncio.run(_service(repo).retrieve("hazing", "ws-1", source_ids=["src-1"]))

    assert repo.segment_calls[0]["source_ids"] == ["src-1"]
    assert repo.lesson_calls[0]["lesson_ids"] is None
    assert repo.lesson_calls[0]["count"] == 6


def test_lesson_ids_narrow_and_raise_count() -> None:
    repo = FakeRepo()

    asyncio.run(_service(repo).retrieve("hazing", "ws-1", lesson_ids=["lesson-1"]))

    assert repo.lesson_calls[0]["lesson_ids"] == ["lesson-1"]
    assert repo.lesson_calls[0]["count"] == 8


def test_empty_query_skips_retrieval() -> None:
    repo = FakeRepo()
    assert asyncio.run(_service(repo).retrieve("   ", "ws-1")) == []
    assert repo.lesson_calls == []


class FakeThreads:
    def __init__(self, thread: dict[str, Any]) -> None:
        self.thread = thread
        self.appended: list[dict[str, Any]] = []

    async def get_thread(self, thread_id: str, workspace_id: str, user_id: str) -> dict[str, Any] | None:
        return self.thread

    async def list_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return []

    async def append_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {"id": f"m{len(self.appended)}", "created_at": datetime.now(UTC).isoformat(), **payload}
        self.appended.append(row)
        return row

    async def touch_thread(self, thread_id: str, workspace_id: str, user_id: str) -> None:
        return None


class FakeAssistant:
    def __init__(self) -> None:
        self.requests: list[AssistantChatRequest] = []

    async def chat(self, request: AssistantChatRequest, workspace_id: str) -> AssistantChatResponse:
        self.requests.append(request)
        return AssistantChatResponse(answer="Answer [1]", grounded=True, citations=[])


def _workspace() -> WorkspaceResponse:
    now = datetime.now(UTC)
    return WorkspaceResponse(
        id="ws-1",
        owner_id="owner-1",
        name="The Basic School",
        slug="the-basic-school",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_thread_lesson_id_reaches_chat_request() -> None:
    now = datetime.now(UTC).isoformat()
    thread = {
        "id": "t1",
        "workspace_id": "ws-1",
        "title": "Decision Making",
        "submode": "tbs",
        "source_id": None,
        "lesson_id": "lesson-1",
        "created_at": now,
        "updated_at": now,
    }
    assistant = FakeAssistant()

    asyncio.run(
        send_discussion_message(
            "t1",
            SendDiscussionMessageRequest(content="Quiz me on ELO 3"),
            _workspace(),
            CurrentUser(id="u1", email="s@example.com", role="student"),
            FakeThreads(thread),  # type: ignore[arg-type]
            assistant,  # type: ignore[arg-type]
        )
    )

    assert assistant.requests[0].lesson_ids == ["lesson-1"]
    assert assistant.requests[0].source_ids is None
