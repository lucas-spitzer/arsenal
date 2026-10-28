import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.assistant import (
    AssistantChatRequest,
    AssistantMessage,
    CreateDiscussionThreadRequest,
    EloCheck,
    SendDiscussionMessageRequest,
)
from app.models.auth import CurrentUser
from app.models.wiki_entry import redact_elo_definitions
from app.models.workspace import WorkspaceResponse
from app.routers.assistant import create_discussion_thread, send_discussion_message
from app.services.assistant import (
    SYSTEM_PROMPTS,
    AssistantService,
    discussion_history,
    elo_check_for_entry,
)


class _Unused:
    pass


def test_tbs_prompt_teaches_from_the_source() -> None:
    prompt = SYSTEM_PROMPTS["discussion:tbs"]

    assert "second lieutenant at The Basic School" in prompt
    assert "Answer ONLY from the SOURCE MATERIAL" in prompt
    assert "Do not invent facts, examples, or doctrine" in prompt
    assert "Ask one question" in prompt
    assert "Do not withhold the answer" in prompt


def test_discussion_defaults_to_the_tbs_instruction() -> None:
    assert CreateDiscussionThreadRequest(title="Patrol base").submode == "tbs"

    service = AssistantService(retrieval=_Unused(), assessments=_Unused())
    prompt = service._system_prompt(AssistantChatRequest(mode="discussion", messages=[]))

    assert prompt == SYSTEM_PROMPTS["discussion:tbs"]


def test_student_wiki_payload_hides_elo_answers() -> None:
    rows = redact_elo_definitions(
        [
            {
                "id": "elo-1",
                "entry_kind": "elo",
                "preferred_label": "Explain the commission.",
                "definition": "A commission is a grant of authority.",
            },
            {
                "id": "term-1",
                "entry_kind": "term",
                "preferred_label": "Commission",
                "definition": "A grant of authority.",
            },
        ]
    )

    assert rows[0]["preferred_label"] == "Explain the commission."
    assert rows[0]["definition"] == ""
    assert rows[1]["definition"] == "A grant of authority."


def test_elo_check_stays_out_of_message_history() -> None:
    answer = "A commission is a grant of authority."
    question = "Explain the commission."
    messages = [
        AssistantMessage(role="assistant", content=question),
        AssistantMessage(role="user", content="It is a grant."),
    ]
    request = AssistantChatRequest(mode="discussion", messages=messages)
    service = AssistantService(retrieval=_Unused(), assessments=_Unused())
    check = EloCheck(question=question, answer=answer)

    prompt = service._system_prompt(request, check)
    history = discussion_history(messages, "SOURCE MATERIAL:\n[1] (Commission) A grant.")

    assert "substantially the same" in prompt
    assert answer in prompt
    assert all(answer not in turn["content"] for turn in history)


def test_elo_check_still_runs_when_retrieval_is_empty() -> None:
    answer = "A commission is a grant of authority."
    seen: dict[str, object] = {}

    class Retrieval:
        async def retrieve(self, *_args: object, **_kwargs: object) -> list[object]:
            return []

    class OpenAI:
        def complete_text(self, **kwargs: object) -> SimpleNamespace:
            seen["system_prompt"] = kwargs["system_prompt"]
            seen["messages"] = kwargs["messages"]
            return SimpleNamespace(content={"text": "That matches."})

    service = AssistantService(
        retrieval=Retrieval(),  # type: ignore[arg-type]
        assessments=_Unused(),
        openai_client=OpenAI(),  # type: ignore[arg-type]
    )
    request = AssistantChatRequest(
        mode="discussion",
        messages=[AssistantMessage(role="user", content="A grant of authority.")],
    )

    asyncio.run(
        service.chat(
            request,
            "ws-1",
            EloCheck(question="Explain the commission.", answer=answer),
        )
    )

    assert answer in str(seen["system_prompt"])
    assert all(answer not in str(turn) for turn in seen["messages"])  # type: ignore[union-attr]


class _Threads:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.messages: list[dict[str, object]] = []

    async def create_thread(self, payload: dict[str, object]) -> dict[str, object]:
        self.created = payload
        return {
            "id": "thread-1",
            "created_at": "2026-10-28T00:00:00Z",
            "updated_at": "2026-10-28T00:00:00Z",
            **payload,
        }

    async def append_message(self, payload: dict[str, object]) -> dict[str, object]:
        row = {"id": "msg-1", "created_at": "2026-10-28T00:00:00Z", "citations": [], **payload}
        self.messages.append(row)
        return row


class _Wiki:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    async def get_for_workspace(self, wiki_entry_id: str, workspace_id: str) -> dict[str, object] | None:
        row = self.row
        if row is None or row.get("id") != wiki_entry_id or row.get("workspace_id") != workspace_id:
            return None
        return row


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


def _user() -> CurrentUser:
    return CurrentUser(id="student-1", email="s@example.com", role="student")


def test_elo_thread_opens_with_the_question() -> None:
    entry = {
        "id": "elo-1",
        "workspace_id": "ws-1",
        "entry_kind": "elo",
        "status": "canonical",
        "preferred_label": "Explain the commission.",
        "definition": "A commission is a grant of authority.",
    }
    threads = _Threads()

    detail = asyncio.run(
        create_discussion_thread(
            CreateDiscussionThreadRequest(title="Explain the commission.", wiki_entry_id="elo-1"),
            _workspace(),
            _user(),
            threads,  # type: ignore[arg-type]
            _Wiki(entry),  # type: ignore[arg-type]
        )
    )

    assert threads.created is not None
    assert threads.created["wiki_entry_id"] == "elo-1"
    assert detail.messages[0].role == "assistant"
    assert detail.messages[0].content == "Explain the commission."
    assert "grant of authority" not in detail.messages[0].content


def test_non_elo_cannot_open_a_checked_discussion() -> None:
    entry = {
        "id": "term-1",
        "workspace_id": "ws-1",
        "entry_kind": "term",
        "status": "canonical",
        "preferred_label": "Commission",
        "definition": "A grant of authority.",
    }

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            create_discussion_thread(
                CreateDiscussionThreadRequest(title="Commission", wiki_entry_id="term-1"),
                _workspace(),
                _user(),
                _Threads(),  # type: ignore[arg-type]
                _Wiki(entry),  # type: ignore[arg-type]
            )
        )

    assert raised.value.status_code == 422
    assert elo_check_for_entry(entry) is None


class _RecordingAssistant:
    def __init__(self) -> None:
        self.check: EloCheck | None = None
        self.messages: list[AssistantMessage] = []

    async def chat(
        self,
        request: AssistantChatRequest,
        workspace_id: str,
        elo_check: EloCheck | None = None,
    ) -> SimpleNamespace:
        self.check = elo_check
        self.messages = request.messages
        return SimpleNamespace(answer="Name the missing part.", grounded=False, citations=[])


class _MessageThreads:
    def __init__(self, thread: dict[str, object]) -> None:
        self.thread = thread
        self.appended: list[dict[str, object]] = []

    async def get_thread(self, thread_id: str, workspace_id: str, user_id: str) -> dict[str, object]:
        return self.thread

    async def list_messages(self, thread_id: str) -> list[dict[str, str]]:
        return [{"role": "assistant", "content": "Explain the commission."}]

    async def append_message(self, payload: dict[str, object]) -> dict[str, object]:
        row = {"id": f"m{len(self.appended)}", "created_at": "2026-10-28T00:00:00Z", **payload}
        self.appended.append(row)
        return row

    async def touch_thread(self, thread_id: str, workspace_id: str, user_id: str) -> None:
        return None


def test_reply_is_checked_against_the_stored_answer() -> None:
    answer = "A commission is a grant of authority."
    assistant = _RecordingAssistant()
    thread = {
        "id": "thread-1",
        "workspace_id": "ws-1",
        "title": "Explain the commission.",
        "submode": "tbs",
        "source_id": None,
        "lesson_id": None,
        "wiki_entry_id": "elo-1",
        "created_at": "2026-10-28T00:00:00Z",
        "updated_at": "2026-10-28T00:00:00Z",
    }

    asyncio.run(
        send_discussion_message(
            "thread-1",
            SendDiscussionMessageRequest(content="It is a grant."),
            _workspace(),
            _user(),
            _MessageThreads(thread),  # type: ignore[arg-type]
            assistant,  # type: ignore[arg-type]
            _Wiki(
                {
                    "id": "elo-1",
                    "workspace_id": "ws-1",
                    "entry_kind": "elo",
                    "status": "canonical",
                    "preferred_label": "Explain the commission.",
                    "definition": answer,
                }
            ),  # type: ignore[arg-type]
        )
    )

    assert assistant.check is not None
    assert assistant.check.answer == answer
    assert all(answer not in message.content for message in assistant.messages)
