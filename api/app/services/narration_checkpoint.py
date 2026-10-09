"""Drop a source's saved narration so the next run synthesizes from the first clip."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.repositories.artifacts import ArtifactRepository
from app.repositories.narration_segments import NarrationSegmentRepository
from app.services.supabase_storage import SupabaseStorageClient
from app.services.tts.factory import narration_override_from_rows


def configured_narration_voice(
    settings: Settings,
    stage_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    """Model and voice the narration worker will use for this workspace."""
    override = narration_override_from_rows(stage_rows)
    if override is not None:
        return override.model, override.voice_id
    narration = settings.narration
    return narration.model_id, narration.voice_id


def _matches_voice(row: dict[str, Any], *, voice_id: str, model_id: str) -> bool:
    manifest = row.get("manifest") or {}
    if not isinstance(manifest, dict):
        return False
    return (
        str(manifest.get("voice_id") or "") == voice_id
        and str(manifest.get("model_id") or "") == model_id
    )


async def clear_narration_checkpoints(
    *,
    workspace_id: str,
    owner_id: str,
    source_ids: list[str],
    model_id: str,
    voice_id: str,
    narration_segments: NarrationSegmentRepository,
    artifacts: ArtifactRepository,
    storage: SupabaseStorageClient,
    bucket: str,
) -> None:
    """Delete narration rows, wavs, and the in-progress artifact for one voice."""
    audio_paths: list[str] = []
    artifact_ids: list[str] = []
    artifact_paths: list[str] = []

    for source_id in source_ids:
        rows = await narration_segments.list_all_for_voice(
            source_id,
            workspace_id,
            owner_id,
            model_id=model_id,
            voice_id=voice_id,
        )
        audio_paths.extend(
            str(row.get("audio_path") or "")
            for row in rows
            if str(row.get("audio_path") or "")
        )
        for artifact in await artifacts.list_narration_for_source(source_id, workspace_id):
            if not _matches_voice(artifact, voice_id=voice_id, model_id=model_id):
                continue
            artifact_id = str(artifact.get("id") or "")
            if artifact_id:
                artifact_ids.append(artifact_id)
            storage_path = str(artifact.get("storage_path") or "")
            if storage_path:
                artifact_paths.append(storage_path)

    for source_id in source_ids:
        await narration_segments.delete_for_voice(
            source_id,
            workspace_id,
            owner_id,
            model_id=model_id,
            voice_id=voice_id,
        )
    for artifact_id in artifact_ids:
        await artifacts.delete(artifact_id)

    await storage.delete_paths(bucket=bucket, paths=[*audio_paths, *artifact_paths])
