import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import Settings, get_settings
from app.access import can_read_library
from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_artifact_repository,
    get_assessment_repository,
    get_knowledge_project_repository,
    get_source_repository,
    get_supabase_storage_client,
    get_wiki_entry_repository,
    get_workspace_repository,
)
from app.dependencies.workspace import require_workspace
from app.knowledge.visuals import storage_path_of, visual_for_response
from app.models.artifact import ArtifactResponse
from app.models.assessment import (
    FlashcardResponse,
    QuizResponse,
    ScenarioResponse,
)
from app.models.auth import CurrentUser
from app.models.knowledge import KnowledgeRunTitle
from app.models.library import LibraryCatalogResponse
from app.models.source import SourceResponse
from app.models.wiki_entry import WikiEntryResponse
from app.models.workspace import WorkspaceResponse
from app.repositories.artifacts import ArtifactRepository
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_projects import KnowledgeProjectRepository
from app.repositories.sources import SourceRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.supabase_storage import SupabaseStorageClient

router = APIRouter(tags=["assessments"])


async def _readable_row(
    row: dict[str, Any] | None,
    user: CurrentUser,
    workspaces: WorkspaceRepository,
) -> dict[str, Any] | None:
    if not row:
        return None
    workspace = await workspaces.get(str(row["workspace_id"]))
    if not workspace or not can_read_library(
        user,
        str(workspace["owner_id"]),
        workspace_name=str(workspace.get("name") or ""),
    ):
        return None
    return row


def _visual(row: dict[str, Any]) -> dict[str, Any] | None:
    visual = row.get("visual")
    return visual if isinstance(visual, dict) else None


async def _with_signed_visuals(
    rows: list[dict[str, Any]],
    storage: SupabaseStorageClient,
    settings: Settings,
) -> list[dict[str, Any]]:
    paths: list[str] = []
    seen: set[str] = set()
    for row in rows:
        path = storage_path_of(_visual(row))
        if path and path not in seen:
            seen.add(path)
            paths.append(path)

    signed: dict[str, str] = {}
    if paths:
        urls = await asyncio.gather(
            *(
                storage.create_signed_url(
                    bucket=settings.sources_bucket,
                    path=path,
                    expires_in=settings.signed_url_expires_seconds,
                )
                for path in paths
            )
        )
        signed = dict(zip(paths, urls, strict=True))

    prepared: list[dict[str, Any]] = []
    for row in rows:
        visual = _visual(row)
        path = storage_path_of(visual)
        prepared.append({**row, "visual": visual_for_response(visual, signed.get(path or ""))})
    return prepared


async def load_library_catalog(
    *,
    workspace_id: str,
    owner_id: str,
    sources: SourceRepository,
    artifacts: ArtifactRepository,
    wiki_entries: WikiEntryRepository,
    assessments: AssessmentRepository,
    projects: KnowledgeProjectRepository,
    storage: SupabaseStorageClient,
    settings: Settings,
) -> LibraryCatalogResponse:
    (
        source_rows,
        artifact_rows,
        wiki_rows,
        flashcard_rows,
        quiz_rows,
        scenario_rows,
        title_rows,
    ) = await asyncio.gather(
        sources.list_for_workspace(workspace_id, owner_id),
        artifacts.list_for_workspace(workspace_id),
        wiki_entries.list_for_workspace(workspace_id),
        assessments.list_flashcards(workspace_id),
        assessments.list_quizzes(workspace_id),
        assessments.list_scenarios(workspace_id),
        projects.list_titles(workspace_id),
    )
    signed_flashcards, signed_quizzes, signed_scenarios = await asyncio.gather(
        _with_signed_visuals(flashcard_rows, storage, settings),
        _with_signed_visuals(quiz_rows, storage, settings),
        _with_signed_visuals(scenario_rows, storage, settings),
    )
    return LibraryCatalogResponse(
        sources=[SourceResponse.model_validate(row) for row in source_rows],
        artifacts=[ArtifactResponse.model_validate(row) for row in artifact_rows],
        wiki_entries=[WikiEntryResponse.model_validate(row) for row in wiki_rows],
        flashcards=[FlashcardResponse.model_validate(row) for row in signed_flashcards],
        quizzes=[QuizResponse.model_validate(row) for row in signed_quizzes],
        scenarios=[ScenarioResponse.model_validate(row) for row in signed_scenarios],
        knowledge_titles=[KnowledgeRunTitle.model_validate(row) for row in title_rows],
    )


@router.get(
    "/workspaces/{workspace_id}/library",
    response_model=LibraryCatalogResponse,
)
async def get_library(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    sources: Annotated[SourceRepository, Depends(get_source_repository)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    projects: Annotated[KnowledgeProjectRepository, Depends(get_knowledge_project_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LibraryCatalogResponse:
    return await load_library_catalog(
        workspace_id=workspace.id,
        owner_id=workspace.owner_id,
        sources=sources,
        artifacts=artifacts,
        wiki_entries=wiki_entries,
        assessments=assessments,
        projects=projects,
        storage=storage,
        settings=settings,
    )


@router.get(
    "/workspaces/{workspace_id}/knowledge-titles",
    response_model=list[KnowledgeRunTitle],
)
async def list_knowledge_titles(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    projects: Annotated[KnowledgeProjectRepository, Depends(get_knowledge_project_repository)],
) -> list[KnowledgeRunTitle]:
    rows = await projects.list_titles(workspace.id)
    return [KnowledgeRunTitle.model_validate(row) for row in rows]


@router.get(
    "/workspaces/{workspace_id}/flashcards",
    response_model=list[FlashcardResponse],
)
async def list_flashcards(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FlashcardResponse]:
    rows = await assessments.list_flashcards(
        workspace.id,
        limit=limit,
        offset=offset,
    )
    signed = await _with_signed_visuals(rows, storage, settings)
    return [FlashcardResponse.model_validate(row) for row in signed]


@router.get("/flashcards/{flashcard_id}", response_model=FlashcardResponse)
async def get_flashcard(
    flashcard_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FlashcardResponse:
    row = await _readable_row(
        await assessments.get_flashcard_by_id(flashcard_id),
        user,
        workspaces,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard not found.",
        )

    signed = await _with_signed_visuals([row], storage, settings)
    return FlashcardResponse.model_validate(signed[0])


@router.get(
    "/workspaces/{workspace_id}/quizzes",
    response_model=list[QuizResponse],
)
async def list_quizzes(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[QuizResponse]:
    rows = await assessments.list_quizzes(
        workspace.id,
        limit=limit,
        offset=offset,
    )
    signed = await _with_signed_visuals(rows, storage, settings)
    return [QuizResponse.model_validate(row) for row in signed]


@router.get("/quizzes/{quiz_id}", response_model=QuizResponse)
async def get_quiz(
    quiz_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QuizResponse:
    row = await _readable_row(
        await assessments.get_quiz_by_id(quiz_id),
        user,
        workspaces,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz question not found.",
        )

    signed = await _with_signed_visuals([row], storage, settings)
    return QuizResponse.model_validate(signed[0])


@router.get(
    "/workspaces/{workspace_id}/scenarios",
    response_model=list[ScenarioResponse],
)
async def list_scenarios(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    _: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScenarioResponse]:
    rows = await assessments.list_scenarios(
        workspace.id,
        limit=limit,
        offset=offset,
    )
    signed = await _with_signed_visuals(rows, storage, settings)
    return [ScenarioResponse.model_validate(row) for row in signed]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScenarioResponse:
    row = await _readable_row(
        await assessments.get_scenario_by_id(scenario_id),
        user,
        workspaces,
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    signed = await _with_signed_visuals([row], storage, settings)
    return ScenarioResponse.model_validate(signed[0])
