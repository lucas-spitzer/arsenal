import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse

from app.artifact_paths import next_available_slug, storage_slug, study_material_file_path
from app.config import Settings, get_settings
from app.dependencies.auth import require_approved_user
from app.dependencies.services import (
    get_production_run_repository,
    get_study_material_repository,
    get_supabase_storage_client,
    get_workspace_repository,
)
from app.dependencies.workspace import require_workspace
from app.mathesys.study_material.assemble import build_render_input
from app.mathesys.study_material.catalog import (
    CatalogError,
    asset_path,
    get_template,
    get_theme,
    load_templates,
    load_themes,
    template_public_payload,
    theme_public_payload,
)
from app.mathesys.study_material.images import (
    ASPECT_RATIOS,
    GOOGLE_IMAGE_SIZES,
    IMAGE_MODELS,
    IMAGE_PROVIDERS,
    OPENAI_QUALITIES,
)
from app.mathesys.study_material.inputs import ComponentFileError, resolve_component_file_mime
from app.mathesys.study_material.render import render_document
from app.models.auth import CurrentUser
from app.models.study_material import (
    ComponentCreate,
    ComponentUpdate,
    StudyMaterialComponentResponse,
    StudyMaterialCreate,
    StudyMaterialResponse,
    StudyMaterialUpdate,
)
from app.models.workspace import WorkspaceResponse
from app.pipeline import STUDY_MATERIAL_TARGET, build_study_material_pipeline
from app.repositories.production_runs import ProductionRunRepository
from app.repositories.study_materials import StudyMaterialRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.queue import enqueue_study_material_finalize, enqueue_study_material_run
from app.services.source_upload import SourceUploadValidationError, sanitize_upload_filename
from app.services.study_materials import (
    BUSY_STATUSES,
    StudyMaterialRuleError,
    component_settings,
    ensure_editable,
    ensure_generatable,
    material_options,
    serialize_material,
    validate_placement,
)
from app.services.supabase_storage import SupabaseStorageClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["study-materials"])

Repo = Annotated[StudyMaterialRepository, Depends(get_study_material_repository)]
User = Annotated[CurrentUser, Depends(require_approved_user)]


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _material_or_404(repo: StudyMaterialRepository, material_id: str, user: CurrentUser) -> dict[str, Any]:
    material = await repo.get_for_owner(material_id, user.id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study material not found.")
    return material


async def _component_or_404(repo: StudyMaterialRepository, material_id: str, component_id: str) -> dict[str, Any]:
    component = await repo.get_component(material_id, component_id)
    if not component:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found.")
    return component


async def _detail(repo: StudyMaterialRepository, material: dict[str, Any]) -> StudyMaterialResponse:
    components = await repo.list_components(str(material["id"]))
    versions = await repo.list_versions(str(material["id"]))
    return StudyMaterialResponse.model_validate(serialize_material(material, components, versions))


def _editable(material: dict[str, Any]) -> None:
    try:
        ensure_editable(material)
    except StudyMaterialRuleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/study-material/catalog")
async def get_catalog(
    _: User,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    return {
        "themes": [theme_public_payload(theme) for theme in load_themes().values()],
        "templates": [template_public_payload(template) for template in load_templates().values()],
        "image": {
            "default_provider": settings.study_material.image_provider,
            "providers": list(IMAGE_PROVIDERS),
            "models": {provider: list(models) for provider, models in IMAGE_MODELS.items()},
            "default_models": {
                "openai": settings.study_material.openai_image_model,
                "google": settings.study_material.google_image_model,
            },
            "aspect_ratios": list(ASPECT_RATIOS),
            "qualities": list(OPENAI_QUALITIES),
            "image_sizes": list(GOOGLE_IMAGE_SIZES),
        },
        "limits": {
            "max_file_bytes": settings.study_material.max_file_bytes,
            "max_files_per_component": settings.study_material.max_files_per_component,
        },
    }


@router.get("/study-material/assets/{asset:path}", include_in_schema=False)
async def get_catalog_asset(asset: str) -> FileResponse:
    """Theme logos for previews. Public so plain <img> tags can load them."""
    try:
        path = asset_path(asset)
    except CatalogError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.") from exc
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/workspaces/{workspace_id}/study-materials", response_model=list[StudyMaterialResponse])
async def list_study_materials(
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: User,
    repo: Repo,
) -> list[StudyMaterialResponse]:
    rows = await repo.list_for_workspace(workspace.id, user.id)
    counts: dict[str, int] = {}
    for component in await repo.list_components_for_workspace(workspace.id):
        key = str(component["study_material_id"])
        counts[key] = counts.get(key, 0) + 1
    return [
        StudyMaterialResponse.model_validate({**row, "component_count": counts.get(str(row["id"]), 0)})
        for row in rows
    ]


@router.post(
    "/workspaces/{workspace_id}/study-materials",
    response_model=StudyMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_study_material(
    payload: StudyMaterialCreate,
    workspace: Annotated[WorkspaceResponse, Depends(require_workspace)],
    user: User,
    repo: Repo,
) -> StudyMaterialResponse:
    try:
        theme = get_theme(payload.theme_id)
        template = get_template(payload.template_id)
        options = material_options(theme, template, payload.options.model_dump())
    except (CatalogError, StudyMaterialRuleError) as exc:
        raise _bad_request(exc) from exc

    title = " ".join(payload.title.split())
    taken = await repo.list_slugs_for_workspace(workspace.id)
    row = await repo.create(
        {
            "workspace_id": workspace.id,
            "owner_id": user.id,
            "title": title,
            "slug": next_available_slug(storage_slug(title, fallback="study-material"), taken),
            "theme_id": theme.id,
            "template_id": template.id,
            "options": options,
            "status": "configuring",
        },
    )
    return await _detail(repo, row)


@router.get("/study-materials/{material_id}", response_model=StudyMaterialResponse)
async def get_study_material(material_id: str, user: User, repo: Repo) -> StudyMaterialResponse:
    return await _detail(repo, await _material_or_404(repo, material_id, user))


@router.patch("/study-materials/{material_id}", response_model=StudyMaterialResponse)
async def update_study_material(
    material_id: str,
    payload: StudyMaterialUpdate,
    user: User,
    repo: Repo,
) -> StudyMaterialResponse:
    material = await _material_or_404(repo, material_id, user)
    _editable(material)
    changes: dict[str, Any] = {}
    if payload.title is not None:
        changes["title"] = " ".join(payload.title.split())
    if payload.options is not None:
        try:
            changes["options"] = material_options(
                get_theme(str(material["theme_id"])),
                get_template(str(material["template_id"])),
                payload.options.model_dump(),
            )
        except StudyMaterialRuleError as exc:
            raise _bad_request(exc) from exc
    updated = await repo.update(material_id, changes) if changes else material
    return await _detail(repo, updated or material)


@router.delete("/study-materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study_material(material_id: str, user: User, repo: Repo) -> None:
    material = await _material_or_404(repo, material_id, user)
    if material["status"] in BUSY_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Wait for the current run to finish.")
    await repo.delete(material_id)


@router.post(
    "/study-materials/{material_id}/components",
    response_model=StudyMaterialComponentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_component(
    material_id: str,
    payload: ComponentCreate,
    user: User,
    repo: Repo,
) -> StudyMaterialComponentResponse:
    material = await _material_or_404(repo, material_id, user)
    _editable(material)
    components = await repo.list_components(material_id)
    try:
        validate_placement(
            get_template(str(material["template_id"])),
            section_id=payload.section_id,
            component_type=payload.component_type,
            section_component_count=sum(1 for row in components if row["section_id"] == payload.section_id),
        )
    except StudyMaterialRuleError as exc:
        raise _bad_request(exc) from exc

    row = await repo.create_component(
        {
            "study_material_id": material_id,
            "workspace_id": material["workspace_id"],
            "section_id": payload.section_id,
            "component_type": payload.component_type,
            "position": 1 + max((int(item.get("position") or 0) for item in components), default=0),
            "instructions": payload.instructions.strip(),
            "settings": component_settings(payload.component_type, payload.settings),
        },
    )
    return StudyMaterialComponentResponse.model_validate(serialize_material(material, [row])["components"][0])


@router.patch(
    "/study-materials/{material_id}/components/{component_id}",
    response_model=StudyMaterialComponentResponse,
)
async def update_component(
    material_id: str,
    component_id: str,
    payload: ComponentUpdate,
    user: User,
    repo: Repo,
) -> StudyMaterialComponentResponse:
    material = await _material_or_404(repo, material_id, user)
    _editable(material)
    component = await _component_or_404(repo, material_id, component_id)
    changes: dict[str, Any] = {}
    if payload.instructions is not None and payload.instructions.strip() != component["instructions"]:
        changes["instructions"] = payload.instructions.strip()
    if payload.settings is not None:
        settings = component_settings(str(component["component_type"]), payload.settings)
        if settings != (component.get("settings") or {}):
            changes["settings"] = settings
    if changes:
        # Changed inputs mean the current output no longer matches; the next run regenerates it.
        changes["active_version_id"] = None
        component = await repo.update_component(component_id, changes) or component
    return StudyMaterialComponentResponse.model_validate(serialize_material(material, [component])["components"][0])


@router.delete(
    "/study-materials/{material_id}/components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_component(material_id: str, component_id: str, user: User, repo: Repo) -> None:
    material = await _material_or_404(repo, material_id, user)
    _editable(material)
    await _component_or_404(repo, material_id, component_id)
    await repo.delete_component(component_id)


@router.post(
    "/study-materials/{material_id}/components/{component_id}/files",
    response_model=StudyMaterialComponentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_component_file(
    material_id: str,
    component_id: str,
    user: User,
    repo: Repo,
    settings: Annotated[Settings, Depends(get_settings)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
    file: UploadFile = File(...),
) -> StudyMaterialComponentResponse:
    material = await _material_or_404(repo, material_id, user)
    _editable(material)
    component = await _component_or_404(repo, material_id, component_id)
    files = list(component.get("files") or [])
    limits = settings.study_material
    if len(files) >= limits.max_files_per_component:
        raise _bad_request(ValueError(f"A component takes at most {limits.max_files_per_component} files."))

    content = await file.read()
    if not content:
        raise _bad_request(ValueError("Uploaded file is empty."))
    if len(content) > limits.max_file_bytes:
        raise _bad_request(ValueError(f"Files are limited to {limits.max_file_bytes // (1024 * 1024)} MB."))
    try:
        filename = sanitize_upload_filename(file.filename or "")
        mime_type = resolve_component_file_mime(filename=filename, content_type=file.content_type, content=content)
    except (SourceUploadValidationError, ComponentFileError) as exc:
        raise _bad_request(exc) from exc

    workspace = await workspaces.get_for_owner(str(material["workspace_id"]), user.id)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    stored_name = f"{len(files) + 1:02d}-{filename}"
    path = study_material_file_path(str(workspace["slug"]), str(material["slug"]), component_id, stored_name)
    await storage.upload(
        bucket=settings.sources_bucket,
        path=path,
        content=content,
        content_type=mime_type,
        upsert=True,
    )
    files.append(
        {
            "id": uuid.uuid4().hex,
            "filename": filename,
            "mime_type": mime_type,
            "storage_path": path,
            "file_size_bytes": len(content),
        },
    )
    updated = await repo.update_component(component_id, {"files": files, "active_version_id": None})
    return StudyMaterialComponentResponse.model_validate(
        serialize_material(material, [updated or component])["components"][0],
    )


@router.delete(
    "/study-materials/{material_id}/components/{component_id}/files/{file_id}",
    response_model=StudyMaterialComponentResponse,
)
async def delete_component_file(
    material_id: str,
    component_id: str,
    file_id: str,
    user: User,
    repo: Repo,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
) -> StudyMaterialComponentResponse:
    material = await _material_or_404(repo, material_id, user)
    _editable(material)
    component = await _component_or_404(repo, material_id, component_id)
    files = list(component.get("files") or [])
    target = next((item for item in files if str(item.get("id")) == file_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    remaining = [item for item in files if item is not target]
    updated = await repo.update_component(component_id, {"files": remaining, "active_version_id": None})
    try:
        await storage.delete(bucket=settings.sources_bucket, path=str(target["storage_path"]))
    except Exception:
        logger.exception("Could not delete component file %s", target.get("storage_path"))
    return StudyMaterialComponentResponse.model_validate(
        serialize_material(material, [updated or component])["components"][0],
    )


@router.post("/study-materials/{material_id}/generate", response_model=StudyMaterialResponse)
async def generate_study_material(
    material_id: str,
    user: User,
    repo: Repo,
    settings: Annotated[Settings, Depends(get_settings)],
    production_runs: Annotated[ProductionRunRepository, Depends(get_production_run_repository)],
) -> StudyMaterialResponse:
    material = await _material_or_404(repo, material_id, user)
    components = await repo.list_components(material_id)
    try:
        ensure_generatable(material, components)
    except StudyMaterialRuleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    run = await production_runs.create(
        {
            "workspace_id": material["workspace_id"],
            "owner_id": user.id,
            "label": material["title"],
            "source_ids": [],
            "target_artifacts": [STUDY_MATERIAL_TARGET],
            "pipeline": build_study_material_pipeline(),
            "status": "queued",
        },
    )
    updated = await repo.update(
        material_id,
        {"production_run_id": run["id"], "status": "generating", "error": None},
    )
    try:
        enqueue_study_material_run(settings, str(run["id"]))
    except Exception as exc:
        logger.exception("Failed to enqueue study material run %s", run["id"])
        await production_runs.update(str(run["id"]), {"status": "failed", "error": f"Failed to enqueue: {exc}"})
        await repo.update(material_id, {"status": material["status"], "error": "Could not queue generation."})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generation could not be queued. Is Redis running?",
        ) from exc
    return await _detail(repo, updated or material)


@router.post("/study-materials/{material_id}/finalize", response_model=StudyMaterialResponse)
async def finalize_study_material(
    material_id: str,
    user: User,
    repo: Repo,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StudyMaterialResponse:
    material = await _material_or_404(repo, material_id, user)
    if material["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a generated draft can be finalized.")
    updated = await repo.update(material_id, {"status": "finalizing", "error": None})
    try:
        enqueue_study_material_finalize(settings, material_id)
    except Exception as exc:
        logger.exception("Failed to enqueue finalize for %s", material_id)
        await repo.update(material_id, {"status": "draft", "error": "Could not queue finalization."})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Finalization could not be queued. Is Redis running?",
        ) from exc
    return await _detail(repo, updated or material)


@router.post("/study-materials/{material_id}/reopen", response_model=StudyMaterialResponse)
async def reopen_study_material(material_id: str, user: User, repo: Repo) -> StudyMaterialResponse:
    material = await _material_or_404(repo, material_id, user)
    if material["status"] != "finalized":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only finalized material can be reopened.")
    updated = await repo.update(material_id, {"status": "draft"})
    return await _detail(repo, updated or material)


@router.get("/study-materials/{material_id}/draft", response_class=HTMLResponse)
async def get_draft_html(
    material_id: str,
    user: User,
    repo: Repo,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[SupabaseStorageClient, Depends(get_supabase_storage_client)],
) -> HTMLResponse:
    material = await _material_or_404(repo, material_id, user)
    components = await repo.list_components(material_id)
    versions = await repo.list_versions(material_id)
    by_id = {str(row["id"]): row for row in versions}

    signed: dict[str, str] = {}
    for component in components:
        version = by_id.get(str(component.get("active_version_id") or ""))
        path = (version or {}).get("output_path")
        if path and path not in signed:
            signed[path] = await storage.create_signed_url(
                bucket=settings.sources_bucket,
                path=path,
                expires_in=settings.signed_url_expires_seconds,
            )

    data = build_render_input(material, components, by_id, image_src=lambda path: signed.get(path, ""))
    return HTMLResponse(render_document(data), headers={"Cache-Control": "no-store"})
