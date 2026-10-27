"""Academy ELO tab: TBS classes, their ELOs, and downloadable materials.

Separate from Knowledge runs: no `sources` rows, no production runs, no
wiki_entries. Files go to the lessons bucket and are indexed for Discussions
into lesson_chunks by the worker.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.config import Settings, get_settings
from app.dependencies.auth import require_admin
from app.dependencies.services import (
    get_lesson_index_queue,
    get_lesson_repository,
    get_supabase_storage_client,
)
from app.dependencies.workspace import require_workspace
from app.errors import is_duplicate_key_error
from app.models.auth import CurrentUser
from app.models.lesson import (
    LessonCreate,
    LessonDownloadResponse,
    LessonLinkCreate,
    LessonObjectivesReplace,
    LessonReindexResponse,
    LessonResourceResponse,
    LessonResourceUpdate,
    LessonResponse,
    LessonUpdate,
)
from app.models.workspace import WorkspaceResponse
from app.repositories.lessons import LessonRepository
from app.services.lesson_files import (
    LessonFileValidationError,
    lesson_storage_path,
    skip_reason,
    validate_lesson_file,
)
from app.services.lesson_index_queue import LessonIndexQueue
from app.services.supabase_rest import SupabaseRestError
from app.services.supabase_storage import SupabaseStorageClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}/lessons", tags=["lessons"])

MAX_FILES_PER_UPLOAD = 20


def _lesson_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")


def _resource_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")


def _duplicate_title() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A class with this title already exists.",
    )


async def _require_lesson(
    lessons: LessonRepository, lesson_id: str, workspace_id: str
) -> dict[str, Any]:
    lesson = await lessons.get(lesson_id, workspace_id)
    if not lesson:
        raise _lesson_not_found()
    return lesson


async def _lesson_response(
    lessons: LessonRepository, lesson_id: str, workspace_id: str
) -> LessonResponse:
    row = await lessons.get_with_children(lesson_id, workspace_id)
    if not row:
        raise _lesson_not_found()
    return LessonResponse.model_validate(row)


@router.get("", response_model=list[LessonResponse])
async def list_lessons(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
) -> list[LessonResponse]:
    rows = await lessons.list_with_children(workspace.id)
    return [LessonResponse.model_validate(row) for row in rows]


@router.post("", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    payload: LessonCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_admin)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    index_queue: Annotated[LessonIndexQueue, Depends(get_lesson_index_queue)],
) -> LessonResponse:
    sort_order = payload.sort_order
    if sort_order is None:
        sort_order = await lessons.next_sort_order(workspace.id)
    try:
        row = await lessons.create(
            {
                "workspace_id": workspace.id,
                "title": payload.title,
                "sort_order": sort_order,
                "notes": payload.notes,
                "created_by": user.id,
            }
        )
    except SupabaseRestError as exc:
        if is_duplicate_key_error(exc):
            raise _duplicate_title() from exc
        raise

    lesson_id = str(row["id"])
    if payload.objectives:
        await lessons.replace_objectives(
            lesson_id, workspace.id, [item.model_dump() for item in payload.objectives]
        )
    index_queue.objectives(lesson_id)
    return await _lesson_response(lessons, lesson_id, workspace.id)


@router.post("/reindex", response_model=LessonReindexResponse, dependencies=[Depends(require_admin)])
async def reindex_all_lessons(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    index_queue: Annotated[LessonIndexQueue, Depends(get_lesson_index_queue)],
) -> LessonReindexResponse:
    rows = await lessons.list_with_children(workspace.id)
    for lesson in rows:
        index_queue.objectives(str(lesson["id"]))

    files = 0
    for resource in await lessons.list_file_resources(workspace.id):
        if skip_reason(str(resource.get("filename") or "")):
            continue
        await lessons.update_resource(
            str(resource["id"]), workspace.id, {"index_status": "pending", "index_error": None}
        )
        index_queue.resource(str(resource["id"]))
        files += 1
    return LessonReindexResponse(lessons=len(rows), files=files)


@router.patch(
    "/{lesson_id}",
    response_model=LessonResponse,
    dependencies=[Depends(require_admin)],
)
async def update_lesson(
    lesson_id: str,
    payload: LessonUpdate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    index_queue: Annotated[LessonIndexQueue, Depends(get_lesson_index_queue)],
) -> LessonResponse:
    existing = await _require_lesson(lessons, lesson_id, workspace.id)
    updates = payload.model_dump(exclude_unset=True)
    for required in ("title", "sort_order"):
        if required in updates and updates[required] is None:
            updates.pop(required)

    if updates:
        try:
            await lessons.update(lesson_id, workspace.id, updates)
        except SupabaseRestError as exc:
            if is_duplicate_key_error(exc):
                raise _duplicate_title() from exc
            raise
        # ELO and file chunks carry the class title in their text.
        if "title" in updates and updates["title"] != existing.get("title"):
            index_queue.objectives(lesson_id)
            for resource in await lessons.list_resources(lesson_id):
                if resource.get("kind") == "file" and not skip_reason(
                    str(resource.get("filename") or "")
                ):
                    index_queue.resource(str(resource["id"]))
    return await _lesson_response(lessons, lesson_id, workspace.id)


@router.delete(
    "/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_lesson(
    lesson_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    settings: Annotated[Settings, Depends(get_settings)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
) -> None:
    await _require_lesson(lessons, lesson_id, workspace.id)
    paths = [
        str(resource["storage_path"])
        for resource in await lessons.list_resources(lesson_id)
        if resource.get("kind") == "file" and resource.get("storage_path")
    ]
    if paths:
        await storage.delete_paths(bucket=settings.lessons_bucket, paths=paths)
    await lessons.delete(lesson_id, workspace.id)


@router.put(
    "/{lesson_id}/objectives",
    response_model=LessonResponse,
    dependencies=[Depends(require_admin)],
)
async def replace_lesson_objectives(
    lesson_id: str,
    payload: LessonObjectivesReplace,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    index_queue: Annotated[LessonIndexQueue, Depends(get_lesson_index_queue)],
) -> LessonResponse:
    await _require_lesson(lessons, lesson_id, workspace.id)
    await lessons.replace_objectives(
        lesson_id, workspace.id, [item.model_dump() for item in payload.objectives]
    )
    index_queue.objectives(lesson_id)
    return await _lesson_response(lessons, lesson_id, workspace.id)


@router.post(
    "/{lesson_id}/resources/files",
    response_model=list[LessonResourceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_lesson_files(
    lesson_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    index_queue: Annotated[LessonIndexQueue, Depends(get_lesson_index_queue)],
    files: list[UploadFile] = File(...),
) -> list[LessonResourceResponse]:
    await _require_lesson(lessons, lesson_id, workspace.id)
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a file.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload at most {MAX_FILES_PER_UPLOAD} files at a time.",
        )

    validated: list[tuple[str, str, bytes]] = []
    for upload in files:
        content = await upload.read()
        try:
            filename, mime_type = validate_lesson_file(
                filename=upload.filename,
                content=content,
                max_bytes=settings.max_lesson_file_bytes,
            )
        except LessonFileValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        validated.append((filename, mime_type, content))

    position = await lessons.next_resource_position(lesson_id)
    created: list[dict[str, Any]] = []
    for filename, mime_type, content in validated:
        storage_path = lesson_storage_path(workspace.slug, lesson_id, filename)
        await storage.upload(
            bucket=settings.lessons_bucket,
            path=storage_path,
            content=content,
            content_type=mime_type,
            upsert=False,
        )
        reason = skip_reason(filename)
        try:
            row = await lessons.create_resource(
                {
                    "lesson_id": lesson_id,
                    "workspace_id": workspace.id,
                    "kind": "file",
                    "label": filename,
                    "position": position,
                    "storage_path": storage_path,
                    "filename": filename,
                    "mime_type": mime_type,
                    "file_size_bytes": len(content),
                    "index_status": "skipped" if reason else "pending",
                    "index_error": reason,
                    "created_by": user.id,
                }
            )
        except Exception:
            try:
                await storage.delete(bucket=settings.lessons_bucket, path=storage_path)
            except Exception:
                logger.exception("Failed to delete orphaned lesson file at %s", storage_path)
            raise
        position += 1
        created.append(row)
        if not reason:
            index_queue.resource(str(row["id"]))

    return [LessonResourceResponse.model_validate(row) for row in created]


@router.post(
    "/{lesson_id}/resources/links",
    response_model=LessonResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_lesson_link(
    lesson_id: str,
    payload: LessonLinkCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: Annotated[CurrentUser, Depends(require_admin)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
) -> LessonResourceResponse:
    await _require_lesson(lessons, lesson_id, workspace.id)
    row = await lessons.create_resource(
        {
            "lesson_id": lesson_id,
            "workspace_id": workspace.id,
            "kind": "link",
            "label": payload.label,
            "url": payload.url,
            "position": await lessons.next_resource_position(lesson_id),
            "index_status": "skipped",
            "index_error": "Login required. Links are not searchable.",
            "created_by": user.id,
        }
    )
    return LessonResourceResponse.model_validate(row)


@router.patch(
    "/{lesson_id}/resources/{resource_id}",
    response_model=LessonResourceResponse,
    dependencies=[Depends(require_admin)],
)
async def update_lesson_resource(
    lesson_id: str,
    resource_id: str,
    payload: LessonResourceUpdate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
) -> LessonResourceResponse:
    existing = await lessons.get_resource(resource_id, lesson_id, workspace.id)
    if not existing:
        raise _resource_not_found()
    updates = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if "url" in updates and existing.get("kind") != "link":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only links have a URL.",
        )
    if not updates:
        return LessonResourceResponse.model_validate(existing)
    row = await lessons.update_resource(resource_id, workspace.id, updates)
    if not row:
        raise _resource_not_found()
    return LessonResourceResponse.model_validate(row)


@router.delete(
    "/{lesson_id}/resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_lesson_resource(
    lesson_id: str,
    resource_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    settings: Annotated[Settings, Depends(get_settings)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
) -> None:
    existing = await lessons.get_resource(resource_id, lesson_id, workspace.id)
    if not existing:
        raise _resource_not_found()
    if existing.get("kind") == "file" and existing.get("storage_path"):
        await storage.delete_paths(
            bucket=settings.lessons_bucket, paths=[str(existing["storage_path"])]
        )
    await lessons.delete_resource(resource_id, workspace.id)


@router.post(
    "/{lesson_id}/resources/{resource_id}/reindex",
    response_model=LessonResourceResponse,
    dependencies=[Depends(require_admin)],
)
async def reindex_lesson_resource(
    lesson_id: str,
    resource_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    index_queue: Annotated[LessonIndexQueue, Depends(get_lesson_index_queue)],
) -> LessonResourceResponse:
    existing = await lessons.get_resource(resource_id, lesson_id, workspace.id)
    if not existing:
        raise _resource_not_found()
    if existing.get("kind") != "file":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Links cannot be indexed.",
        )
    reason = skip_reason(str(existing.get("filename") or ""))
    if reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)
    row = await lessons.update_resource(
        resource_id, workspace.id, {"index_status": "pending", "index_error": None}
    )
    index_queue.resource(resource_id)
    return LessonResourceResponse.model_validate(row or existing)


@router.get(
    "/{lesson_id}/resources/{resource_id}/download",
    response_model=LessonDownloadResponse,
)
async def download_lesson_resource(
    lesson_id: str,
    resource_id: str,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    settings: Annotated[Settings, Depends(get_settings)],
    lessons: Annotated[LessonRepository, Depends(get_lesson_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
) -> LessonDownloadResponse:
    existing = await lessons.get_resource(resource_id, lesson_id, workspace.id)
    if not existing:
        raise _resource_not_found()
    if existing.get("kind") == "link":
        return LessonDownloadResponse(url=str(existing["url"]))
    url = await storage.create_signed_url(
        bucket=settings.lessons_bucket,
        path=str(existing["storage_path"]),
        expires_in=settings.signed_url_expires_seconds,
        download_name=str(existing.get("filename") or "lesson-file"),
    )
    return LessonDownloadResponse(url=url)
