from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_source_repository,
    get_wiki_authoring_service,
    get_wiki_entry_repository,
)
from app.dependencies.workspace import require_workspace
from app.models.auth import CurrentUser
from app.models.wiki_entry import (
    WikiDisputeResponse,
    WikiEntryCreate,
    WikiEntryResponse,
    WikiEntryUpdate,
    WikiReviseProposal,
    WikiReviseRequest,
)
from app.models.wiki_ingest import (
    WikiIngestBatchResponse,
    WikiIngestCreate,
    batch_row_to_response,
)
from app.models.workspace import WorkspaceResponse
from app.repositories.sources import SourceRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.services.wiki_authoring import (
    WikiAuthoringError,
    WikiAuthoringService,
    WikiIngestNotFoundError,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/wiki", tags=["wiki"])


@router.get("/entries", response_model=list[WikiEntryResponse])
async def list_wiki_entries(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WikiEntryResponse]:
    rows = await wiki_entries.list_for_workspace(
        workspace.id,
        status=status_filter,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [WikiEntryResponse.model_validate(row) for row in rows]


@router.post(
    "/entries",
    response_model=WikiEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_wiki_entry(
    payload: WikiEntryCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
) -> WikiEntryResponse:
    try:
        row = await authoring.create_entry(
            workspace.id,
            preferred_label=payload.preferred_label,
            definition=payload.definition,
            entry_kind=payload.entry_kind,
            importance=payload.importance,
            aliases=payload.aliases,
            pronunciation=payload.pronunciation,
            origin=payload.origin,
        )
    except WikiAuthoringError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return WikiEntryResponse.model_validate(row)


@router.get("/entries/{wiki_entry_id}", response_model=WikiEntryResponse)
async def get_wiki_entry(
    wiki_entry_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
) -> WikiEntryResponse:
    row = await wiki_entries.get_for_workspace(wiki_entry_id, workspace.id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wiki entry not found.",
        )

    return WikiEntryResponse.model_validate(row)


@router.patch("/entries/{wiki_entry_id}", response_model=WikiEntryResponse)
async def update_wiki_entry(
    wiki_entry_id: str,
    payload: WikiEntryUpdate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
) -> WikiEntryResponse:
    updates = payload.model_dump(exclude_none=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    try:
        row = await authoring.update_entry(wiki_entry_id, workspace.id, updates)
    except WikiIngestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return WikiEntryResponse.model_validate(row)


@router.post("/entries/{wiki_entry_id}/revise", response_model=WikiReviseProposal)
async def revise_wiki_entry(
    wiki_entry_id: str,
    payload: WikiReviseRequest,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
) -> WikiReviseProposal:
    try:
        proposal = await authoring.revise_entry(
            wiki_entry_id,
            workspace.id,
            payload.instruction,
        )
    except WikiIngestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WikiAuthoringError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return WikiReviseProposal.model_validate(proposal)


@router.delete("/entries/{wiki_entry_id}", response_model=WikiEntryResponse)
async def deprecate_wiki_entry(
    wiki_entry_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
) -> WikiEntryResponse:
    """Soft delete: canonical → deprecated (QnGen and the assistant filter it out)."""
    try:
        row = await authoring.deprecate_entry(wiki_entry_id, workspace.id)
    except WikiIngestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return WikiEntryResponse.model_validate(row)


@router.get("/disputes", response_model=list[WikiDisputeResponse])
async def list_wiki_disputes(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
    status_filter: Annotated[str | None, Query(alias="status")] = "open",
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[WikiDisputeResponse]:
    rows = await wiki_entries.list_disputes_for_workspace(
        workspace.id,
        status=status_filter,
        limit=limit,
    )
    return [WikiDisputeResponse.model_validate(row) for row in rows]


# ---------------------------------------------------------------------------
# Ingest batches: leftover API for notes/files → wiki_knowledge production run.
# The UI path is New Run with Wiki Knowledge; the selected source file is the notes.
# ---------------------------------------------------------------------------


@router.post(
    "/ingest-batches",
    response_model=WikiIngestBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ingest_batch(
    payload: WikiIngestCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    sources: Annotated[SourceRepository, Depends(get_source_repository)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
) -> WikiIngestBatchResponse:
    found = await sources.get_many_for_workspace(
        [payload.source_id],
        workspace.id,
        user.id,
    )

    if not found:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_id is invalid for this workspace.",
        )

    try:
        row = await authoring.create_batch(payload, workspace.id, owner_id=user.id)
    except WikiAuthoringError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return batch_row_to_response(row)


@router.post(
    "/ingest-batches/from-files",
    response_model=WikiIngestBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ingest_batch_from_files(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    sources: Annotated[SourceRepository, Depends(get_source_repository)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
    source_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    chapter_hint: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
) -> WikiIngestBatchResponse:
    found = await sources.get_many_for_workspace(
        [source_id],
        workspace.id,
        user.id,
    )
    if not found:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_id is invalid for this workspace.",
        )

    max_bytes = authoring.settings.wiki_authoring.max_attachment_bytes
    uploads: list[tuple[str, str | None, bytes]] = []
    for upload in files:
        filename = upload.filename
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file must include a filename.",
            )
        # Cap the read so oversized uploads fail without buffering the full body.
        content = await upload.read(max_bytes + 1)
        if len(content) > max_bytes:
            max_megabytes = max_bytes // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Uploaded file '{filename}' exceeds the "
                    f"{max_megabytes} MB limit."
                ),
            )
        uploads.append((filename, upload.content_type, content))

    try:
        row = await authoring.create_file_batch(
            workspace_id=workspace.id,
            owner_id=user.id,
            source_id=source_id,
            chapter_hint=(chapter_hint.strip() if chapter_hint else None),
            title=(title.strip() if title else None),
            files=uploads,
        )
    except WikiAuthoringError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return batch_row_to_response(row)


@router.get("/ingest-batches", response_model=list[WikiIngestBatchResponse])
async def list_ingest_batches(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[WikiIngestBatchResponse]:
    rows = await authoring.batches.list_for_workspace(
        workspace.id,
        status=status_filter,
        limit=limit,
    )
    return [batch_row_to_response(row) for row in rows]


@router.get("/ingest-batches/{batch_id}", response_model=WikiIngestBatchResponse)
async def get_ingest_batch(
    batch_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    authoring: Annotated[WikiAuthoringService, Depends(get_wiki_authoring_service)],
) -> WikiIngestBatchResponse:
    row = await authoring.batches.get_for_workspace(batch_id, workspace.id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingest batch not found.",
        )

    return batch_row_to_response(row)
