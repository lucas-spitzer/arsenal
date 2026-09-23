"""Generate Narration stage: per-chapter TTS with word timings.

Walks each source's document_chapters in reading order and synthesizes one
clip per chapter for the configured voice (idempotent re-runs). If a chapter's
joined paragraph text exceeds the provider character cap, it is packed into
the fewest clips that fit, always splitting on paragraph boundaries. A single
paragraph over the cap is skipped.

Audio is stored at `{workspace}/{source}/audio/{voice_id}/{chapter}-{clip}.{mp3|wav}`.
Each paragraph keeps a `narration_segments` row pointing at that shared file,
with word timings on the clip timeline so the Reader can highlight and seek.

The downloadable artifact is a small JSON manifest (chapter grouping, timings,
and sources-bucket audio paths) — not a zip of clips.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.artifact_paths import (
    OUTPUT_FILENAMES,
    downloadable_artifact_path,
    location_from_source,
    narration_clip_path,
)
from app.services.api_pricing import cost_tts_usage
from app.services.cartesia_client import CartesiaError
from app.config import get_settings
from app.services.elevenlabs_client import ElevenLabsError, force_align_audio
from app.services.gemini_tts_client import GeminiTtsError
from app.services.speechify_client import SpeechifyError
from app.services.tts.alignment import timing_quality
from app.services.tts.factory import TtsClient, get_tts_client
from app.services.tts.types import WordTiming
from app.services.stage_run_billing import stage_run_completion_fields
from app.worker.db import WorkerDatabase
from app.worker.storage import WorkerStorage

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def matching_narration_artifacts(
    rows: list[dict[str, Any]],
    *,
    voice_id: str,
    model_id: str,
) -> list[dict[str, Any]]:
    """Return narration_audio rows for this voice/model, oldest first."""
    matched: list[dict[str, Any]] = []
    for row in rows:
        manifest = row.get("manifest") or {}
        if not isinstance(manifest, dict):
            continue
        if str(manifest.get("voice_id") or "") != voice_id:
            continue
        if str(manifest.get("model_id") or "") != model_id:
            continue
        matched.append(row)
    matched.sort(key=lambda row: str(row.get("created_at") or ""))
    return matched


_CLIP_JOIN = "\n\n"


def _audio_extension(client: TtsClient) -> str:
    content_type = getattr(client, "audio_content_type", "audio/mpeg")
    if content_type == "audio/wav":
        return "wav"
    return "mp3"


def _paragraph_text(row: dict[str, Any]) -> str:
    return str(row.get("text") or "").strip()


def _is_speakable(text: str) -> bool:
    return any(character.isalnum() for character in text)


def _joined_clip_text(paragraphs: list[dict[str, Any]]) -> str:
    return _CLIP_JOIN.join(
        text
        for text in (_paragraph_text(row) for row in paragraphs)
        if _is_speakable(text)
    )


def _can_skip_gemini_clip(
    exc: BaseException, *, narrated: int, reused: int
) -> bool:
    """Skip a mid-run Gemini flake instead of failing the whole stage.

    A 400 on the first synthesis is more likely a bad voice/model and should
    still fail the stage. After at least one clip has landed, the same generic
    INVALID_ARGUMENT is a known preview-model flake.
    """
    if narrated == 0 and reused == 0:
        return False
    message = str(exc)
    return "INVALID_ARGUMENT" in message or "INTERNAL" in message or (
        "missing audio inline data" in message
    )


def pack_chapter_clips(
    paragraphs: list[dict[str, Any]],
    max_chars: int,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]], int]:
    """Pack chapter paragraphs into TTS clips that fit under `max_chars`.

    Returns (clips, oversize_paragraphs, empty_count). Clips never split a
    paragraph. A paragraph longer than the cap is omitted rather than truncated.
    """
    clips: list[list[dict[str, Any]]] = []
    oversize: list[dict[str, Any]] = []
    empty_count = 0
    current: list[dict[str, Any]] = []
    current_len = 0

    for row in paragraphs:
        text = _paragraph_text(row)
        if not _is_speakable(text):
            empty_count += 1
            continue
        if len(text) > max_chars:
            if current:
                clips.append(current)
                current = []
                current_len = 0
            oversize.append(row)
            continue
        extra = len(text) if not current else len(_CLIP_JOIN) + len(text)
        if current and current_len + extra > max_chars:
            clips.append(current)
            current = [row]
            current_len = len(text)
        else:
            current.append(row)
            current_len += extra

    if current:
        clips.append(current)
    return clips, oversize, empty_count


def assign_words_to_paragraphs(
    paragraphs: list[dict[str, Any]],
    words: list[WordTiming],
) -> list[list[WordTiming]]:
    """Assign clip-level timings by source character span, never list position."""
    if words and any(
        word.start_char is None or word.end_char is None for word in words
    ):
        raise ValueError("Word timings are missing source character spans.")

    assigned: list[list[WordTiming]] = []
    paragraph_start = 0
    assigned_count = 0
    for row in paragraphs:
        text = _paragraph_text(row)
        paragraph_end = paragraph_start + len(text)
        chunk = [
            word
            for word in words
            if word.start_char is not None
            and paragraph_start <= word.start_char < paragraph_end
        ]
        expected_count = len(text.split())
        if len(chunk) != expected_count:
            raise ValueError(
                f"Alignment mapped {len(chunk)} words to paragraph {row.get('id')} "
                f"but expected {expected_count}."
            )
        assigned.append(
            [
                WordTiming(
                    index=i,
                    word=word.word,
                    start=word.start,
                    end=word.end,
                    start_char=(
                        word.start_char - paragraph_start
                        if word.start_char is not None
                        else None
                    ),
                    end_char=(
                        word.end_char - paragraph_start
                        if word.end_char is not None
                        else None
                    ),
                )
                for i, word in enumerate(chunk)
            ]
        )
        assigned_count += len(chunk)
        paragraph_start = paragraph_end + len(_CLIP_JOIN)
    if assigned_count != len(words):
        raise ValueError(
            "Clip alignment contains words outside the source paragraph ranges: "
            f"{len(words)} timings, {assigned_count} assigned."
        )
    return assigned


def _progress_output(
    *,
    done: int,
    total: int,
    narrated: int,
    reused: int,
    skipped: int,
    character_count: int,
    voice_id: str,
    model_id: str,
) -> dict[str, Any]:
    """Stage-run output shape used both mid-run (live UI) and at completion."""
    return {
        "summary": f"{done}/{total} clips",
        "segments_done": done,
        "segments_total": total,
        "segments_narrated": narrated,
        "segments_reused": reused,
        "segments_skipped": skipped,
        "character_count": character_count,
        "voice_id": voice_id,
        "model_id": model_id,
    }


def _paragraph_rows_for_chapter(
    chapter: dict[str, Any],
    segments: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        segments[segment_id]
        for segment_id in chapter.get("segment_ids") or []
        if segment_id in segments and segments[segment_id].get("kind") == "paragraph"
    ]


class NarrationStageExecutor:
    """Stage: GENERATE-NARRATION -- synthesize read-while-listen audio."""

    STAGE_ID = "generate-narration"
    STAGE_VERSION = "1.0"
    MODULE = "mathesys"

    def __init__(
        self,
        db: WorkerDatabase | None = None,
        storage: WorkerStorage | None = None,
        client: TtsClient | None = None,
        max_segment_chars: int | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.storage = storage or WorkerStorage()
        self._client = client
        self._max_segment_chars = max_segment_chars
        self._last_progress: dict[str, Any] | None = None

    @property
    def client(self) -> TtsClient:
        if self._client is None:
            self._client = get_tts_client()
        return self._client

    @property
    def max_segment_chars(self) -> int:
        if self._max_segment_chars is not None:
            return self._max_segment_chars
        return self.client.max_segment_chars

    def run_for_source(
        self,
        *,
        production_run_id: str,
        workspace_id: str,
        source: dict[str, Any],
    ) -> str:
        stage_run = self.db.create_stage_run(
            {
                "production_run_id": production_run_id,
                "workspace_id": workspace_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
                "module": self.MODULE,
                "status": "running",
                "inputs": {
                    "source_id": source["id"],
                    "voice_id": self.client.voice_id,
                    "model_id": self.client.model_id,
                },
                "started_at": utc_now_iso(),
            }
        )
        stage_run_id = stage_run["id"]

        try:
            output, character_count, publish_context = self._narrate_source(
                workspace_id=workspace_id,
                source=source,
                stage_run_id=stage_run_id,
            )
            artifact_file = self._publish_artifact(
                workspace_id=workspace_id,
                production_run_id=production_run_id,
                stage_run_id=stage_run_id,
                source=source,
                complete=True,
                clips_total=int(output.get("segments_total") or 0) or None,
                **publish_context,
            )
            promoted: dict[str, Any] = {"source_ids": [source["id"]]}
            if artifact_file:
                output["files"] = [artifact_file]
                promoted["artifact_ids"] = [artifact_file["artifact_id"]]
            extra_calls = (
                [
                    cost_tts_usage(
                        provider=getattr(self.client, "provider", "elevenlabs"),
                        model=self.client.model_id,
                        character_count=character_count,
                    )
                ]
                if character_count
                else []
            )
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": output,
                    "promoted": promoted,
                    **stage_run_completion_fields(
                        {"model": self.client.model_id, "token_usage": {}},
                        extra_calls=extra_calls,
                    ),
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id
        except Exception as exc:
            logger.exception("Narration stage run %s failed", stage_run_id)
            fail_payload: dict[str, Any] = {
                "status": "failed",
                "error": str(exc),
                "completed_at": utc_now_iso(),
            }
            try:
                progress = self._last_progress or {}
                artifact_file = self._publish_artifact(
                    workspace_id=workspace_id,
                    production_run_id=production_run_id,
                    stage_run_id=stage_run_id,
                    source=source,
                    complete=False,
                    clips_total=int(progress.get("segments_total") or 0) or None,
                )
            except Exception:
                logger.exception(
                    "Failed to publish partial narration artifact for stage run %s",
                    stage_run_id,
                )
                artifact_file = None
            if artifact_file:
                fail_payload["promoted"] = {
                    "source_ids": [source["id"]],
                    "artifact_ids": [artifact_file["artifact_id"]],
                }
            self.db.update_stage_run(stage_run_id, fail_payload)
            raise

    def _publish_progress(
        self,
        stage_run_id: str,
        *,
        done: int,
        total: int,
        narrated: int,
        reused: int,
        skipped: int,
        character_count: int,
    ) -> dict[str, Any]:
        output = _progress_output(
            done=done,
            total=total,
            narrated=narrated,
            reused=reused,
            skipped=skipped,
            character_count=character_count,
            voice_id=self.client.voice_id,
            model_id=self.client.model_id,
        )
        self._last_progress = output
        self.db.update_stage_run(stage_run_id, {"output": output})
        return output

    def _narrate_source(
        self,
        *,
        workspace_id: str,
        source: dict[str, Any],
        stage_run_id: str,
    ) -> tuple[dict[str, Any], int, dict[str, Any]]:
        if not self.client.enabled:
            provider = getattr(self.client, "provider", "tts")
            key_name = {
                "speechify": "SPEECHIFY_API_KEY",
                "elevenlabs": "ELEVENLABS_API_KEY",
                "cartesia": "CARTESIA_API_KEY",
                "google": "GEMINI_API_KEY",
            }.get(provider, "TTS_API_KEY")
            error_cls = {
                "speechify": SpeechifyError,
                "elevenlabs": ElevenLabsError,
                "cartesia": CartesiaError,
                "google": GeminiTtsError,
            }.get(provider, RuntimeError)
            raise error_cls(
                f"{key_name} is not configured; cannot generate narration."
            )

        source_id = source["id"]
        location_from_source(source)

        segments = {
            row["id"]: row for row in self.db.list_ndr_segments_for_source(source_id)
        }
        chapters = self.db.list_document_chapters_for_source(source_id)
        if not chapters:
            raise RuntimeError(
                f"Source {source_id} has no document chapters; run the base pipeline first."
            )

        existing_rows = {
            row["segment_id"]: row
            for row in self.db.list_narration_segments_for_source(
                source_id,
                self.client.voice_id,
                self.client.model_id,
            )
        }

        packed: list[tuple[dict[str, Any], int, list[dict[str, Any]]]] = []
        skipped = 0
        for chapter in chapters:
            paragraph_rows = _paragraph_rows_for_chapter(chapter, segments)
            clips, oversize, empty_count = pack_chapter_clips(
                paragraph_rows, self.max_segment_chars
            )
            skipped += empty_count
            for row in oversize:
                logger.warning(
                    "Paragraph %s is %d chars (> %d); skipping narration for it.",
                    row["id"],
                    len(_paragraph_text(row)),
                    self.max_segment_chars,
                )
                skipped += 1
            for clip_index, clip_rows in enumerate(clips):
                packed.append((chapter, clip_index, clip_rows))

        clips_total = len(packed)
        narrated = 0
        reused = 0
        done = 0
        character_count = 0
        previous_request_ids: list[str] = []

        def publish() -> dict[str, Any]:
            return self._publish_progress(
                stage_run_id,
                done=done,
                total=clips_total,
                narrated=narrated,
                reused=reused,
                skipped=skipped,
                character_count=character_count,
            )

        # Seed progress so the console shows 0/N before the first TTS round-trip.
        output = publish()

        last_chapter_id: str | None = None
        for chapter, clip_index, clip_rows in packed:
            chapter_id = str(chapter.get("id") or "")
            if last_chapter_id is not None and chapter_id != last_chapter_id:
                previous_request_ids = []
            last_chapter_id = chapter_id

            audio_path = narration_clip_path(
                source,
                getattr(self.client, "provider", "tts"),
                self.client.model_id,
                self.client.voice_id,
                chapter_id,
                clip_index,
                extension=_audio_extension(self.client),
            )
            clip_ids = [str(row["id"]) for row in clip_rows]
            if clip_ids and all(
                existing_rows.get(str(row["id"]), {}).get("audio_path") == audio_path
                and existing_rows.get(str(row["id"]), {}).get("model_id")
                == self.client.model_id
                and existing_rows.get(str(row["id"]), {}).get("text_hash")
                == hashlib.sha256(_paragraph_text(row).encode("utf-8")).hexdigest()
                for row in clip_rows
            ):
                reused += 1
                previous_request_ids = []
                done += 1
                output = publish()
                continue

            text = _joined_clip_text(clip_rows)
            try:
                result = self.client.synthesize_with_timestamps(
                    text,
                    previous_request_ids=previous_request_ids,
                )
            except GeminiTtsError as exc:
                if not _can_skip_gemini_clip(
                    exc, narrated=narrated, reused=reused
                ):
                    raise
                logger.warning(
                    "Skipping Gemini clip %d for source %s chapter %s "
                    "(%d chars): %s",
                    clip_index,
                    source_id,
                    chapter_id,
                    len(text),
                    exc,
                )
                skipped += 1
                previous_request_ids = []
                done += 1
                output = publish()
                continue
            quality = result.alignment_quality or timing_quality(
                text,
                result.words,
                result.duration_seconds,
            )
            estimated_result = result
            estimated_quality = quality
            needs_forced_alignment = (
                result.alignment_source == "estimated"
                or not bool(quality.get("valid"))
            )
            elevenlabs_key = get_settings().narration.elevenlabs_api_key
            if needs_forced_alignment and elevenlabs_key:
                try:
                    aligned_words, forced_quality = force_align_audio(
                        audio=result.audio,
                        text=text,
                        api_key=elevenlabs_key,
                        content_type=getattr(
                            self.client,
                            "audio_content_type",
                            "audio/mpeg",
                        ),
                    )
                    if forced_quality.get("valid"):
                        result = replace(
                            result,
                            words=aligned_words,
                            alignment_source="forced",
                            alignment_quality=forced_quality,
                        )
                        quality = forced_quality
                    else:
                        logger.warning(
                            "Forced alignment was invalid for source %s chapter %s "
                            "clip %d; keeping %s timings. %s",
                            source_id,
                            chapter_id,
                            clip_index,
                            result.alignment_source,
                            forced_quality,
                        )
                except ElevenLabsError:
                    logger.exception(
                        "Forced alignment failed for source %s chapter %s clip %d.",
                        source_id,
                        chapter_id,
                        clip_index,
                    )
            if result.alignment_source != "estimated" and not quality.get("valid"):
                if estimated_result.alignment_source == "estimated":
                    logger.warning(
                        "Reverting to estimated alignment for source %s chapter %s "
                        "clip %d. %s",
                        source_id,
                        chapter_id,
                        clip_index,
                        quality,
                    )
                    result = estimated_result
                    quality = estimated_quality
                else:
                    raise RuntimeError(
                        f"Invalid {getattr(self.client, 'provider', 'TTS')} alignment "
                        f"for chapter {chapter_id} clip {clip_index}: {quality}"
                    )
            per_paragraph_words = assign_words_to_paragraphs(clip_rows, result.words)

            self.storage.upload(
                audio_path,
                result.audio,
                bucket=self.storage.sources_bucket,
                content_type=getattr(self.client, "audio_content_type", "audio/mpeg"),
            )
            for row, words in zip(clip_rows, per_paragraph_words, strict=True):
                self.db.upsert_narration_segment(
                    {
                        "workspace_id": workspace_id,
                        "source_id": source_id,
                        "chapter_id": chapter.get("id"),
                        "segment_id": row["id"],
                        "provider": getattr(self.client, "provider", "tts"),
                        "voice_id": self.client.voice_id,
                        "model_id": self.client.model_id,
                        "text_hash": hashlib.sha256(
                            _paragraph_text(row).encode("utf-8")
                        ).hexdigest(),
                        "audio_path": audio_path,
                        "duration_seconds": result.duration_seconds,
                        "words": [word.to_dict() for word in words],
                        "alignment_source": result.alignment_source,
                        "alignment_quality": quality,
                        "request_id": result.request_id,
                        "character_count": result.character_cost,
                        "updated_at": utc_now_iso(),
                    }
                )
                existing_rows[str(row["id"])] = {"audio_path": audio_path}

            narrated += 1
            character_count += result.character_cost
            if result.request_id:
                previous_request_ids = (previous_request_ids + [result.request_id])[-3:]

            done += 1
            output = publish()

        publish_context = {
            "chapters": chapters,
            "segments": segments,
        }
        return output, character_count, publish_context

    def _artifact_title(self, source: dict[str, Any]) -> str:
        research = (source.get("source_metadata") or {}).get("research") or {}
        if not isinstance(research, dict):
            research = {}
        return str(research.get("title") or source.get("filename") or "Untitled")

    def _publish_artifact(
        self,
        *,
        workspace_id: str,
        production_run_id: str,
        stage_run_id: str,
        source: dict[str, Any],
        chapters: list[dict[str, Any]] | None = None,
        segments: dict[str, dict[str, Any]] | None = None,
        complete: bool = True,
        clips_total: int | None = None,
    ) -> dict[str, Any] | None:
        """Publish a JSON manifest of narrated chapter clips as the downloadable artifact.

        Per-chapter MP3s stay in the sources bucket (Reader source of truth). The
        artifact is a small export: chapter grouping, word timings, and each
        paragraph's shared audio_path — usable without embedding audio bytes.

        Upserts one row per source+model+voice. Called on success and after a
        partial failure so clips already written still have an `artifacts` row.
        """
        source_id = source["id"]
        if chapters is None:
            chapters = self.db.list_document_chapters_for_source(source_id)
        if segments is None:
            segments = {
                row["id"]: row
                for row in self.db.list_ndr_segments_for_source(source_id)
            }
        rows = self.db.list_narration_segments_for_source(
            source_id,
            self.client.voice_id,
            self.client.model_id,
        )
        by_segment = {row["segment_id"]: row for row in rows}
        if not by_segment:
            return None

        title = self._artifact_title(source)
        filename = OUTPUT_FILENAMES["narration_audio"]

        manifest_chapters: list[dict[str, Any]] = []
        total_duration = 0.0
        segment_total = 0
        billed_paths: set[str] = set()

        for chapter in chapters:
            entries: list[dict[str, Any]] = []
            for segment_id in chapter.get("segment_ids") or []:
                row = by_segment.get(segment_id)
                if row is None:
                    continue
                segment = segments.get(segment_id) or {}
                sequence_index = int(segment.get("sequence_index") or 0)
                duration = float(row.get("duration_seconds") or 0)
                path = str(row.get("audio_path") or "")
                if path and path not in billed_paths:
                    billed_paths.add(path)
                    total_duration += duration
                segment_total += 1
                entries.append(
                    {
                        "segment_id": segment_id,
                        "sequence_index": sequence_index,
                        "audio_path": row.get("audio_path"),
                        "duration_seconds": duration,
                        "character_count": row.get("character_count"),
                        "text_hash": row.get("text_hash"),
                        "alignment_source": row.get("alignment_source", "provider"),
                        "alignment_quality": row.get("alignment_quality") or {},
                        "words": row.get("words") or [],
                    }
                )
            if entries:
                manifest_chapters.append(
                    {
                        "title": chapter.get("title"),
                        "sequence_index": chapter.get("sequence_index"),
                        "segments": entries,
                    }
                )

        now = utc_now_iso()
        status = "complete" if complete else "in_progress"
        clip_count = len(billed_paths)
        resolved_clips_total = clips_total if clips_total and clips_total > 0 else clip_count
        existing_rows = matching_narration_artifacts(
            self.db.list_artifacts_for_source(
                source_id, artifact_type="narration_audio"
            ),
            voice_id=self.client.voice_id,
            model_id=self.client.model_id,
        )
        keep = existing_rows[0] if existing_rows else None
        generated_at = now
        if keep:
            previous_manifest = keep.get("manifest") or {}
            if isinstance(previous_manifest, dict):
                previous_generated = str(previous_manifest.get("generated_at") or "")
                if previous_generated:
                    generated_at = previous_generated
            for extra in existing_rows[1:]:
                extra_id = str(extra.get("id") or "")
                if extra_id:
                    self.db.delete_artifact(extra_id)

        manifest = {
            "source_id": source["id"],
            "title": title,
            "provider": getattr(self.client, "provider", "tts"),
            "voice_id": self.client.voice_id,
            "model_id": self.client.model_id,
            "status": status,
            "generated_at": generated_at,
            "updated_at": now,
            "segment_count": segment_total,
            "clip_count": clip_count,
            "clips_total": resolved_clips_total,
            "total_duration_seconds": round(total_duration, 3),
            "chapters": manifest_chapters,
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        storage_path = downloadable_artifact_path(source, "narration_audio")
        payload = {
            "workspace_id": workspace_id,
            "source_id": source["id"],
            "production_run_id": production_run_id,
            "artifact_type": "narration_audio",
            "format": "json",
            "filename": filename,
            "storage_path": storage_path,
            "file_size_bytes": len(manifest_bytes),
            "manifest": {
                "voice_id": self.client.voice_id,
                "model_id": self.client.model_id,
                "status": status,
                "generated_at": generated_at,
                "updated_at": now,
                "segment_count": segment_total,
                "clip_count": clip_count,
                "clips_total": resolved_clips_total,
                "chapter_count": len(manifest_chapters),
                "chapter_titles": [c["title"] for c in manifest_chapters],
                "total_duration_seconds": round(total_duration, 3),
            },
            "origin": {
                "stage_run_id": stage_run_id,
                "stage_id": self.STAGE_ID,
                "stage_version": self.STAGE_VERSION,
            },
        }
        if keep:
            artifact = self.db.update_artifact(str(keep["id"]), payload)
        else:
            artifact = self.db.create_artifact(payload)
        artifact_id = artifact["id"]
        self.storage.upload(
            storage_path,
            manifest_bytes,
            bucket=self.storage.sources_bucket,
            content_type="application/json",
        )

        return {
            "artifact_id": artifact_id,
            "filename": filename,
            "storage_path": storage_path,
            "file_size_bytes": len(manifest_bytes),
        }
