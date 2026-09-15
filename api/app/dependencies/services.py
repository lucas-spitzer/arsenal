from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.repositories.artifacts import ArtifactRepository
from app.repositories.assessments import AssessmentRepository
from app.repositories.discussions import DiscussionRepository
from app.repositories.document_chapters import DocumentChapterRepository
from app.repositories.narration_segments import NarrationSegmentRepository
from app.repositories.ndr_segments import NdrSegmentRepository
from app.repositories.production_runs import ProductionRunRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.sources import SourceRepository
from app.repositories.stage_runs import StageRunRepository
from app.repositories.stage_settings import StageSettingsRepository
from app.repositories.stages import StageRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.repositories.wiki_ingest_batches import WikiIngestBatchRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.assistant import AssistantService
from app.services.retrieval import RetrievalService
from app.services.supabase_rest import SupabaseRestClient
from app.services.supabase_storage import SupabaseStorageClient
from app.services.wiki_authoring import WikiAuthoringService


def get_supabase_rest_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SupabaseRestClient:
    return SupabaseRestClient(settings)


def get_supabase_storage_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SupabaseStorageClient:
    return SupabaseStorageClient(settings)


def get_workspace_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> WorkspaceRepository:
    return WorkspaceRepository(db)


def get_stage_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> StageRepository:
    return StageRepository(db)


def get_stage_settings_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> StageSettingsRepository:
    return StageSettingsRepository(db)


def get_source_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> SourceRepository:
    return SourceRepository(db)


def get_production_run_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> ProductionRunRepository:
    return ProductionRunRepository(db)


def get_stage_run_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> StageRunRepository:
    return StageRunRepository(db)


def get_ndr_segment_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> NdrSegmentRepository:
    return NdrSegmentRepository(db)


def get_narration_segment_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> NarrationSegmentRepository:
    return NarrationSegmentRepository(db)


def get_document_chapter_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> DocumentChapterRepository:
    return DocumentChapterRepository(db)


def get_wiki_entry_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> WikiEntryRepository:
    return WikiEntryRepository(db)


def get_artifact_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> ArtifactRepository:
    return ArtifactRepository(db)


def get_assessment_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> AssessmentRepository:
    return AssessmentRepository(db)


def get_retrieval_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> RetrievalRepository:
    return RetrievalRepository(db)


def get_retrieval_service(
    repository: Annotated[RetrievalRepository, Depends(get_retrieval_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RetrievalService:
    return RetrievalService(
        repository,
        threshold=settings.assistant.match_threshold,
        segment_count=settings.assistant.segment_count,
        wiki_count=settings.assistant.wiki_count,
    )


def get_wiki_ingest_batch_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> WikiIngestBatchRepository:
    return WikiIngestBatchRepository(db)


def get_wiki_authoring_service(
    wiki_entries: Annotated[WikiEntryRepository, Depends(get_wiki_entry_repository)],
    batches: Annotated[WikiIngestBatchRepository, Depends(get_wiki_ingest_batch_repository)],
    production_runs: Annotated[ProductionRunRepository, Depends(get_production_run_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WikiAuthoringService:
    return WikiAuthoringService(
        wiki_entries=wiki_entries,
        batches=batches,
        production_runs=production_runs,
        settings=settings,
    )


def get_discussion_repository(
    db: Annotated[SupabaseRestClient, Depends(get_supabase_rest_client)],
) -> DiscussionRepository:
    return DiscussionRepository(db)


def get_assistant_service(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantService:
    return AssistantService(
        retrieval=retrieval,
        assessments=assessments,
        chat_model=settings.assistant.chat_model,
    )
