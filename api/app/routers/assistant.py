from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.access import is_admin
from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_assistant_service,
    get_discussion_repository,
    get_wiki_entry_repository,
)
from app.dependencies.workspace import require_workspace
from app.models.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantMessage,
    CreateDiscussionThreadRequest,
    DiscussionMessageResponse,
    DiscussionSubmode,
    DiscussionThreadDetailResponse,
    DiscussionThreadResponse,
    SendDiscussionMessageRequest,
    SendDiscussionMessageResponse,
    UpdateDiscussionThreadRequest,
)
from app.models.auth import CurrentUser
from app.models.workspace import WorkspaceResponse
from app.repositories.discussions import DiscussionRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.services.assistant import AssistantService, elo_check_for_entry, short_thread_title

router = APIRouter(
    prefix="/workspaces/{workspace_id}/assistant",
    tags=["assistant"],
)


@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    request: AssistantChatRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    assistant: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantChatResponse:
    return await assistant.chat(request, workspace.id)


# --- Persisted discussion threads ------------------------------------------


def _thread_row(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "title": short_thread_title(str(row.get("title") or ""))}


def _thread_model(row: dict[str, Any]) -> DiscussionThreadResponse:
    return DiscussionThreadResponse(**_thread_row(row))


def _message_model(row: dict[str, Any]) -> DiscussionMessageResponse:
    return DiscussionMessageResponse(**row)


async def _require_thread(
    threads: DiscussionRepository,
    thread_id: str,
    workspace_id: str,
    user_id: str,
) -> dict[str, Any]:
    thread = await threads.get_thread(thread_id, workspace_id, user_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion thread not found.",
        )
    return thread


@router.get("/threads", response_model=list[DiscussionThreadResponse])
async def list_discussion_threads(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    threads: Annotated[DiscussionRepository, Depends(get_discussion_repository)],
) -> list[DiscussionThreadResponse]:
    rows = await threads.list_threads(workspace.id, user.id)
    return [_thread_model(row) for row in rows]


@router.post(
    "/threads",
    response_model=DiscussionThreadDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_discussion_thread(
    request: CreateDiscussionThreadRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    threads: Annotated[DiscussionRepository, Depends(get_discussion_repository)],
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
    assistant: Annotated[AssistantService, Depends(get_assistant_service)],
) -> DiscussionThreadDetailResponse:
    title = short_thread_title(request.title)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Thread title is required.",
        )

    wiki_entry_id: str | None = None
    opener = request.seed_prompt.strip() if request.seed_prompt else ""
    if request.wiki_entry_id:
        entry = await wiki_entries.get_for_workspace(request.wiki_entry_id, workspace.id)
        check = elo_check_for_entry(entry)
        if check is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Discussion starter must be a canonical ELO.",
            )
        wiki_entry_id = request.wiki_entry_id
        opener = check.question

    submode: DiscussionSubmode = request.submode if is_admin(user) else "tbs"
    row = await threads.create_thread(
        {
            "workspace_id": workspace.id,
            "user_id": user.id,
            "title": title,
            "submode": submode,
            "source_id": request.source_id,
            "wiki_entry_id": wiki_entry_id,
            **({"lesson_id": request.lesson_id} if request.lesson_id else {}),
        }
    )

    messages: list[DiscussionMessageResponse] = []
    if wiki_entry_id and opener:
        asked = await threads.append_message(
            {
                "thread_id": row["id"],
                "role": "user",
                "content": opener,
                "citations": [],
            }
        )
        messages.append(_message_model(asked))
        # The student asked the ELO. Answer it as a normal turn. The private
        # expected answer is only for judging a later reply, not this prompt.
        reply = await assistant.chat(
            AssistantChatRequest(
                mode="discussion",
                submode=submode,
                source_ids=[request.source_id] if request.source_id else None,
                lesson_ids=[request.lesson_id] if request.lesson_id else None,
                messages=[AssistantMessage(role="user", content=opener)],
            ),
            workspace.id,
        )
        answered = await threads.append_message(
            {
                "thread_id": row["id"],
                "role": "assistant",
                "content": reply.answer,
                "citations": [citation.model_dump() for citation in reply.citations],
            }
        )
        messages.append(_message_model(answered))
        await threads.touch_thread(row["id"], workspace.id, user.id)
    elif opener:
        seeded = await threads.append_message(
            {
                "thread_id": row["id"],
                "role": "assistant",
                "content": opener,
                "citations": [],
            }
        )
        messages.append(_message_model(seeded))

    return DiscussionThreadDetailResponse(**_thread_row(row), messages=messages)


@router.get("/threads/{thread_id}", response_model=DiscussionThreadDetailResponse)
async def get_discussion_thread(
    thread_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    threads: Annotated[DiscussionRepository, Depends(get_discussion_repository)],
) -> DiscussionThreadDetailResponse:
    thread = await _require_thread(threads, thread_id, workspace.id, user.id)
    rows = await threads.list_messages(thread_id)
    return DiscussionThreadDetailResponse(
        **_thread_row(thread),
        messages=[_message_model(row) for row in rows],
    )


@router.patch("/threads/{thread_id}", response_model=DiscussionThreadResponse)
async def update_discussion_thread(
    thread_id: str,
    request: UpdateDiscussionThreadRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    threads: Annotated[DiscussionRepository, Depends(get_discussion_repository)],
) -> DiscussionThreadResponse:
    await _require_thread(threads, thread_id, workspace.id, user.id)

    payload: dict[str, Any] = {}
    if request.title is not None and short_thread_title(request.title):
        payload["title"] = short_thread_title(request.title)
    if request.submode is not None:
        if not is_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Discussion style is limited to the Academics officer.",
            )
        payload["submode"] = request.submode

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nothing to update.",
        )

    updated = await threads.update_thread(thread_id, workspace.id, user.id, payload)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion thread not found.",
        )
    return _thread_model(updated)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discussion_thread(
    thread_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    threads: Annotated[DiscussionRepository, Depends(get_discussion_repository)],
) -> None:
    await _require_thread(threads, thread_id, workspace.id, user.id)
    await threads.delete_thread(thread_id, workspace.id, user.id)


@router.post(
    "/threads/{thread_id}/messages",
    response_model=SendDiscussionMessageResponse,
)
async def send_discussion_message(
    thread_id: str,
    request: SendDiscussionMessageRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    threads: Annotated[DiscussionRepository, Depends(get_discussion_repository)],
    assistant: Annotated[AssistantService, Depends(get_assistant_service)],
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
) -> SendDiscussionMessageResponse:
    content = request.content.strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message content is required.",
        )

    thread = await _require_thread(threads, thread_id, workspace.id, user.id)

    history_rows = await threads.list_messages(thread_id)
    user_row = await threads.append_message(
        {
            "thread_id": thread_id,
            "role": "user",
            "content": content,
            "citations": [],
        }
    )

    chat_request = AssistantChatRequest(
        mode="discussion",
        submode=thread["submode"] if is_admin(user) else "tbs",
        source_ids=[thread["source_id"]] if thread.get("source_id") else None,
        lesson_ids=[thread["lesson_id"]] if thread.get("lesson_id") else None,
        messages=[
            AssistantMessage(role=row["role"], content=row["content"])
            for row in history_rows
        ]
        + [AssistantMessage(role="user", content=content)],
    )
    elo_check = None
    wiki_entry_id = thread.get("wiki_entry_id")
    if wiki_entry_id:
        entry = await wiki_entries.get_for_workspace(str(wiki_entry_id), workspace.id)
        elo_check = elo_check_for_entry(entry)
    response = await assistant.chat(chat_request, workspace.id, elo_check)

    assistant_row = await threads.append_message(
        {
            "thread_id": thread_id,
            "role": "assistant",
            "content": response.answer,
            "citations": [c.model_dump() for c in response.citations],
        }
    )

    await threads.touch_thread(thread_id, workspace.id, user.id)

    return SendDiscussionMessageResponse(
        user_message=_message_model(user_row),
        assistant_message=_message_model(assistant_row),
        grounded=response.grounded,
    )
