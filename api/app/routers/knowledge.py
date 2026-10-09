from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_knowledge_project_service,
    get_source_repository,
    get_supabase_storage_client,
    get_workspace_repository,
)
from app.dependencies.workspace import require_workspace
from app.knowledge.visuals import VisualError
from app.models.auth import CurrentUser
from app.models.knowledge import (
    KnowledgeBatchRequest,
    KnowledgeFlashcardSave,
    KnowledgePlanUpdate,
    KnowledgeProjectDetail,
    KnowledgeProjectSummary,
    KnowledgeProjectUpdate,
    KnowledgeQuestionSave,
    KnowledgeScenarioSave,
    KnowledgeVariantsRequest,
)
from app.models.workspace import WorkspaceResponse
from app.repositories.sources import SourceRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.knowledge_projects import KnowledgeProjectError, KnowledgeProjectService
from app.services.supabase_storage import SupabaseStorageClient
from app.services.wiki_transcription import WikiTranscriptionError

router = APIRouter(tags=["knowledge"])
User = Annotated[CurrentUser, Depends(require_approved_user)]
Service = Annotated[KnowledgeProjectService, Depends(get_knowledge_project_service)]
Storage = Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)]


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _project_or_404(service: KnowledgeProjectService, project_id: str, user: CurrentUser) -> dict:
    project = await service.projects.get_for_owner(project_id, user.id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge project not found.")
    return project


async def _detail(
    service: KnowledgeProjectService,
    project: dict,
    storage: SupabaseStorageClient,
) -> KnowledgeProjectDetail:
    payload = await service.detail(project, storage=storage)
    return KnowledgeProjectDetail.model_validate(payload)


@router.get(
    "/workspaces/{workspace_id}/knowledge-projects",
    response_model=list[KnowledgeProjectSummary],
)
async def list_knowledge_projects(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: User,
    service: Service,
) -> list[KnowledgeProjectSummary]:
    rows = await service.projects.list_for_workspace(workspace.id, user.id)
    return [KnowledgeProjectSummary.model_validate(row) for row in rows]


@router.post(
    "/workspaces/{workspace_id}/knowledge-projects",
    response_model=KnowledgeProjectDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_project(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: User,
    service: Service,
    storage: Storage,
    sources: Annotated[SourceRepository, Depends(get_source_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    title: Annotated[str, Form()],
    source_id: Annotated[str, Form()],
    raw_notes: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> KnowledgeProjectDetail:
    source = await sources.get_for_workspace(source_id, workspace.id, user.id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    owner_workspace = await workspaces.get_for_owner(workspace.id, user.id)
    if not owner_workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    content = await file.read() if file and file.filename else None
    try:
        project = await service.create(
            workspace_id=workspace.id,
            owner_id=user.id,
            workspace_slug=str(owner_workspace["slug"]),
            title=title,
            source=source,
            raw_notes=raw_notes,
            filename=file.filename if file else None,
            content_type=file.content_type if file else None,
            content=content,
            storage=storage,
        )
    except (KnowledgeProjectError, WikiTranscriptionError, VisualError) as exc:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if "queued" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return await _detail(service, project, storage)


@router.get("/knowledge-projects/{project_id}", response_model=KnowledgeProjectDetail)
async def get_knowledge_project(
    project_id: str,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    return await _detail(service, project, storage)


@router.patch("/knowledge-projects/{project_id}", response_model=KnowledgeProjectDetail)
async def update_knowledge_project(
    project_id: str,
    payload: KnowledgeProjectUpdate,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    try:
        updated = await service.update_switches(
            project,
            draft_questions=payload.draft_questions,
            draft_scenarios=payload.draft_scenarios,
            batch_instructions=payload.batch_instructions,
        )
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(service, updated, storage)


@router.post("/knowledge-projects/{project_id}/draft", response_model=KnowledgeProjectDetail)
async def draft_knowledge_project(
    project_id: str,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    try:
        updated = await service.start_draft(project)
    except KnowledgeProjectError as exc:
        status_code = status.HTTP_409_CONFLICT if "Turn on" in str(exc) or "not composing" in str(exc) else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return await _detail(service, updated, storage)


@router.post("/knowledge-projects/{project_id}/flashcards", response_model=KnowledgeProjectDetail)
async def make_knowledge_flashcards(
    project_id: str,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    try:
        updated = await service.make_flashcards(project)
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    refreshed = await service.projects.get_for_owner(project_id, user.id)
    return await _detail(service, refreshed or updated, storage)


@router.post("/knowledge-projects/{project_id}/batches", response_model=KnowledgeProjectDetail)
async def generate_knowledge_batch(
    project_id: str,
    payload: KnowledgeBatchRequest,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    try:
        updated = await service.generate_batch(
            project,
            kind=payload.kind,
            category=payload.category,
            item_format=payload.format,
            instructions=payload.instructions,
            per_entry=payload.per_entry,
            bloom_level=payload.bloom_level,
            mode=payload.mode,
        )
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    refreshed = await service.projects.get_for_owner(project_id, user.id)
    return await _detail(service, refreshed or updated, storage)


@router.post("/knowledge-projects/{project_id}/variants", response_model=KnowledgeProjectDetail)
async def generate_knowledge_variants(
    project_id: str,
    payload: KnowledgeVariantsRequest,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    try:
        updated = await service.generate_variants(
            project,
            wiki_entry_id=payload.wiki_entry_id,
            kind=payload.kind,
            item_format=payload.format,
            count=payload.count,
            mix=payload.mix,
            bloom_level=payload.bloom_level,
            instructions=payload.instructions,
        )
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    refreshed = await service.projects.get_for_owner(project_id, user.id)
    return await _detail(service, refreshed or updated, storage)


async def _plan_or_404(service: KnowledgeProjectService, project_id: str, plan_id: str) -> dict:
    plan = await service.projects.get_plan(project_id, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    return plan


@router.put("/knowledge-projects/{project_id}/plans/{plan_id}/question", response_model=KnowledgeProjectDetail)
async def save_knowledge_question(
    project_id: str,
    plan_id: str,
    payload: KnowledgeQuestionSave,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await _plan_or_404(service, project_id, plan_id)
    try:
        await service.save_item(project, plan, kind="question", payload=payload.model_dump())
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(service, project, storage)


@router.put("/knowledge-projects/{project_id}/plans/{plan_id}/scenario", response_model=KnowledgeProjectDetail)
async def save_knowledge_scenario(
    project_id: str,
    plan_id: str,
    payload: KnowledgeScenarioSave,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await _plan_or_404(service, project_id, plan_id)
    try:
        await service.save_item(project, plan, kind="scenario", payload=payload.model_dump())
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(service, project, storage)


@router.put("/knowledge-projects/{project_id}/plans/{plan_id}/flashcard", response_model=KnowledgeProjectDetail)
async def save_knowledge_flashcard(
    project_id: str,
    plan_id: str,
    payload: KnowledgeFlashcardSave,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await _plan_or_404(service, project_id, plan_id)
    try:
        await service.save_flashcard(project, plan, front=payload.front, back=payload.back)
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(service, project, storage)


@router.post("/knowledge-projects/{project_id}/plans/{plan_id}/duplicate", response_model=KnowledgeProjectDetail)
async def duplicate_knowledge_item(
    project_id: str,
    plan_id: str,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await _plan_or_404(service, project_id, plan_id)
    try:
        await service.duplicate_item(project, plan)
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(service, project, storage)


@router.delete("/knowledge-projects/{project_id}/plans/{plan_id}", response_model=KnowledgeProjectDetail)
async def delete_knowledge_item(
    project_id: str,
    plan_id: str,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await _plan_or_404(service, project_id, plan_id)
    try:
        await service.delete_item(project, plan)
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(service, project, storage)


@router.post("/knowledge-projects/{project_id}/visuals", response_model=KnowledgeProjectDetail)
async def attach_knowledge_visuals(
    project_id: str,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    try:
        updated = await service.start_attach(project)
    except KnowledgeProjectError as exc:
        status_code = status.HTTP_409_CONFLICT if "not ready" in str(exc) else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return await _detail(service, updated, storage)


@router.patch(
    "/knowledge-projects/{project_id}/plans/{plan_id}",
    response_model=KnowledgeProjectDetail,
)
async def update_knowledge_plan(
    project_id: str,
    plan_id: str,
    payload: KnowledgePlanUpdate,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await service.projects.get_plan(project_id, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    try:
        if payload.enabled is not None:
            await service.set_plan_enabled(project, plan, payload.enabled)
        if payload.layout is not None:
            await service.set_plan_layout(project, plan, payload.layout)
        if payload.instructions is not None:
            await service.set_plan_instructions(project, plan, payload.instructions)
        if payload.clear_draft:
            await service.set_plan_draft(project, plan, None)
        elif payload.draft is not None:
            await service.set_plan_draft(project, plan, payload.draft)
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    refreshed = await service.projects.get_for_owner(project_id, user.id)
    return await _detail(service, refreshed or project, storage)


@router.post(
    "/knowledge-projects/{project_id}/plans/{plan_id}/visual",
    response_model=KnowledgeProjectDetail,
)
async def upload_plan_visual(
    project_id: str,
    plan_id: str,
    user: User,
    service: Service,
    storage: Storage,
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    kind: Annotated[str, Form()] = "diagram",
    placement: Annotated[str, Form()] = "",
    alt: Annotated[str, Form()] = "",
    file: UploadFile = File(...),
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await service.projects.get_plan(project_id, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    workspace = await workspaces.get_for_owner(str(project["workspace_id"]), user.id)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    content = await file.read()
    try:
        await service.save_visual(
            project=project,
            plan=plan,
            workspace_slug=str(workspace["slug"]),
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            kind=kind,
            placement=placement or None,
            alt=alt,
            storage=storage,
        )
    except (KnowledgeProjectError, VisualError) as exc:
        code = status.HTTP_409_CONFLICT if isinstance(exc, KnowledgeProjectError) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    refreshed = await service.projects.get_for_owner(project_id, user.id)
    return await _detail(service, refreshed or project, storage)


@router.delete(
    "/knowledge-projects/{project_id}/plans/{plan_id}/visual",
    response_model=KnowledgeProjectDetail,
)
async def delete_plan_visual(
    project_id: str,
    plan_id: str,
    user: User,
    service: Service,
    storage: Storage,
) -> KnowledgeProjectDetail:
    project = await _project_or_404(service, project_id, user)
    plan = await service.projects.get_plan(project_id, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    try:
        await service.clear_visual(project=project, plan=plan, storage=storage)
    except KnowledgeProjectError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    refreshed = await service.projects.get_for_owner(project_id, user.id)
    return await _detail(service, refreshed or project, storage)
