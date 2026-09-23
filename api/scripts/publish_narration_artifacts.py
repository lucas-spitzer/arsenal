"""Create missing narration_audio artifact rows from existing clips.

generate-narration used to publish the artifacts row only after every segment
succeeded, so a mid-run TTS failure left MP3s in `narration_segments` with no
downloadable artifact. This script publishes a JSON manifest for each
(source, voice, model) pair that has clips but no matching `narration_audio`
row. An in-progress row counts as already published; a later Aidio run
refreshes that same row instead of inserting.

    python -m scripts.publish_narration_artifacts
    python -m scripts.publish_narration_artifacts --dry-run
"""

from __future__ import annotations

import argparse
from typing import Any

from app.config import get_settings
from app.services.supabase_rest import SupabaseRestClient
from app.services.tts.factory import get_tts_client
from app.worker.db import WorkerDatabase
from app.worker.narration_executor import NarrationStageExecutor, matching_narration_artifacts
from app.worker.storage import WorkerStorage

BATCH = 500


def _variant_already_published(
    artifacts: list[dict[str, Any]],
    *,
    voice_id: str,
    model_id: str,
) -> bool:
    return bool(
        matching_narration_artifacts(
            artifacts, voice_id=voice_id, model_id=model_id
        )
    )


async def migrate(*, dry_run: bool) -> int:
    settings = get_settings()
    rest = SupabaseRestClient(settings)
    db = WorkerDatabase()
    storage = WorkerStorage()
    published = 0
    seen: set[tuple[str, str, str]] = set()
    offset = 0

    while True:
        rows = await rest.select_many(
            "narration_segments",
            columns="source_id,workspace_id,voice_id,model_id",
            order="created_at.asc",
            limit=BATCH,
            offset=offset,
        )
        if not rows:
            break

        for row in rows:
            source_id = str(row.get("source_id") or "")
            voice_id = str(row.get("voice_id") or "")
            model_id = str(row.get("model_id") or "")
            if not source_id or not voice_id:
                continue
            key = (source_id, voice_id, model_id)
            if key in seen:
                continue
            seen.add(key)

            existing = db.list_artifacts_for_source(
                source_id, artifact_type="narration_audio"
            )
            if _variant_already_published(
                existing, voice_id=voice_id, model_id=model_id
            ):
                print(
                    f"  skip {source_id} voice {voice_id} model {model_id}: "
                    "already published"
                )
                continue

            source = await rest.select_one("sources", filters={"id": f"eq.{source_id}"})
            if not source or not source.get("storage_path"):
                print(f"  skip {source_id}: source missing storage_path")
                continue

            stage_runs = await rest.select_many(
                "stage_runs",
                filters={
                    "stage_id": "eq.generate-narration",
                    "workspace_id": f"eq.{source['workspace_id']}",
                },
                columns="id,production_run_id,inputs",
                order="created_at.desc",
                limit=20,
            )
            stage_run = next(
                (
                    run
                    for run in stage_runs
                    if str((run.get("inputs") or {}).get("source_id") or "") == source_id
                    and str((run.get("inputs") or {}).get("voice_id") or "") == voice_id
                ),
                stage_runs[0] if stage_runs else None,
            )
            production_run_id = str(
                (stage_run or {}).get("production_run_id")
                or source.get("production_run_id")
                or ""
            )
            stage_run_id = str((stage_run or {}).get("id") or "backfill")
            if not production_run_id:
                print(f"  skip {source_id}: no production_run_id")
                continue

            print(
                f"  publish {source_id} voice {voice_id} model {model_id}"
                + (" (dry-run)" if dry_run else "")
            )
            if dry_run:
                published += 1
                continue

            executor = NarrationStageExecutor(
                db=db,
                storage=storage,
                client=get_tts_client(model=model_id or None, voice_id=voice_id),
            )
            file_info = executor._publish_artifact(
                workspace_id=str(source["workspace_id"]),
                production_run_id=production_run_id,
                stage_run_id=stage_run_id,
                source=source,
            )
            if file_info:
                print(f"    artifact {file_info['artifact_id']} -> {file_info['storage_path']}")
                published += 1
            else:
                print(f"    skip {source_id}: no narration rows for this voice")

        if len(rows) < BATCH:
            break
        offset += BATCH

    return published


async def main_async(*, dry_run: bool) -> None:
    print(
        "Publishing missing narration_audio artifacts"
        + (" (dry-run)" if dry_run else "")
        + "..."
    )
    count = await migrate(dry_run=dry_run)
    print(f"Done: {count} artifact(s) {'would publish' if dry_run else 'published'}.")


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(
        description=(
            "Create narration_audio artifact rows for sources that already "
            "have narration_segments but no matching artifacts row."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned publishes without writing rows or files.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
