"""Generate Narration stage: per-chapter TTS with word timings.

Walks each source's document_chapters in reading order and synthesizes one
clip per chapter for the configured voice (idempotent re-runs). If a chapter's
joined paragraph text exceeds the provider character cap, it is packed into
the fewest clips that fit, always splitting on paragraph boundaries. A single
paragraph over the cap is skipped. When a provider refuses a clip, its
paragraphs are tried one at a time; a paragraph that is still refused stays
missing.

A provider quota or rate limit pauses the stage (NarrationPaused) instead of
failing it; the pipeline schedules a resume.

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
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.artifact_paths import (
    OUTPUT_FILENAMES,
    downloadable_artifact_path,
    location_from_source,
    narration_clip_path,
    narration_paragraph_path,
)
from app.services.api_pricing import cost_tts_usage
from app.services.cartesia_client import CartesiaError
from app.config import get_settings
from app.services.elevenlabs_client import ElevenLabsError, force_align_audio
from app.services.gemini_tts_client import GeminiQuotaError, GeminiTtsError
from app.services.speechify_client import SpeechifyError
from app.services.tts.alignment import timing_quality
from app.services.tts.factory import TtsClient, get_tts_client
from app.services.tts.types import NarrationResult, TtsQuotaError, WordTiming
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


def _stops_run(exc: BaseException) -> bool:
    """Rate and quota limits end the run; retrying other clips only spends quota."""
    if isinstance(exc, TtsQuotaError):
        return True
    message = str(exc)
    return "429" in message or "RESOURCE_EXHAUSTED" in message


_QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")
_RATE_LIMIT_RESUME_DELAY = timedelta(minutes=15)


class NarrationPaused(TtsQuotaError):
    """The stage stopped on a provider quota; resume `stage_run_id` at `resume_at`."""

    def __init__(self, message: str, *, resume_at: datetime, stage_run_id: str) -> None:
        super().__init__(message, resume_at=resume_at)
        self.stage_run_id = stage_run_id


def _next_quota_reset(now: datetime) -> datetime:
    """Gemini's per-day request quota resets at midnight Pacific time."""
    local = now.astimezone(_QUOTA_TIMEZONE)
    midnight = datetime.combine(local.date() + timedelta(days=1), time(0), _QUOTA_TIMEZONE)
    return midnight.astimezone(UTC)


def quota_resume_at(exc: BaseException, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    resume_at = getattr(exc, "resume_at", None)
    if isinstance(resume_at, datetime):
        return resume_at
    if isinstance(exc, GeminiQuotaError):
        return _next_quota_reset(current)
    return current + _RATE_LIMIT_RESUME_DELAY


def quota_stop_message(
    exc: BaseException,
    *,
    paragraphs_saved: int,
    paragraphs_total: int,
    now: datetime | None = None,
) -> str:
    resume_at = quota_resume_at(exc, now)
    if "budget" in str(exc):
        reason = "Request budget for this run reached"
    elif isinstance(exc, GeminiQuotaError):
        reason = "Daily Gemini quota reached"
    else:
        reason = "Narration provider rate limit reached"
    return (
        f"{reason}. {paragraphs_saved} of {paragraphs_total} paragraphs saved. "
        f"Resumes after {resume_at.strftime('%Y-%m-%d %H:%M')} UTC."
    )


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _saved_paragraph(
    row: dict[str, Any],
    existing_rows: dict[str, dict[str, Any]],
    model_id: str,
) -> dict[str, Any] | None:
    """A paragraph already spoken for this model, whatever file it landed in."""
    existing = existing_rows.get(str(row.get("id") or ""))
    if not existing or not existing.get("audio_path"):
        return None
    if str(existing.get("model_id") or "") != model_id:
        return None
    if existing.get("text_hash") != _text_hash(_paragraph_text(row)):
        return None
    return existing


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
    total: int,
    narrated: int,
    reused: int,
    skipped: int,
    character_count: int,
    voice_id: str,
    model_id: str,
    paragraphs_total: int = 0,
    paragraphs_saved: int = 0,
) -> dict[str, Any]:
    """Stage-run output shape used both mid-run (live UI) and at completion.

    ``segments_done`` is clips that have audio for this source: ones reused
    from an earlier run plus ones synthesized now. Skipped attempts are not
    counted, and reused clips are not synthesized again. ``paragraphs_missing``
    is what the Reader will still skip.
    """
    covered = narrated + reused
    missing = max(paragraphs_total - paragraphs_saved, 0)
    summary = f"{covered}/{total} clips"
    if missing:
        summary += f", {missing} of {paragraphs_total} paragraphs missing"
    return {
        "summary": summary,
        "paragraphs_total": paragraphs_total,
        "paragraphs_saved": paragraphs_saved,
        "paragraphs_missing": missing,
        "segments_done": covered,
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
        self._alignment_requests = 0
        self._billed_before = 0

    def _usage_fields(self, character_count: int) -> dict[str, Any]:
        provider = getattr(self.client, "provider", "elevenlabs")
        extra_calls: list[dict[str, Any]] = []
        if character_count:
            extra_calls.append(
                cost_tts_usage(
                    provider=provider,
                    model=self.client.model_id,
                    character_count=character_count,
                )
            )
        if self._alignment_requests:
            extra_calls.append(
                {
                    "provider": "elevenlabs",
                    "model": "forced-alignment",
                    "request_count": self._alignment_requests,
                    "cost_usd": 0,
                }
            )
        return stage_run_completion_fields(
            {
                "model": self.client.model_id,
                "provider": provider,
                "token_usage": {},
            },
            extra_calls=extra_calls,
        )

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
        stage_run_id: str | None = None,
    ) -> str:
        """Narrate one source. Pass `stage_run_id` to resume a paused stage run.

        Raises NarrationPaused (stage run left `queued`) on a provider quota.
        """
        self._alignment_requests = 0
        self._billed_before = 0
        self._last_progress = None
        if hasattr(self.client, "requests_made"):
            self.client.requests_made = 0
        if stage_run_id:
            prior = self._stage_run_output(production_run_id, stage_run_id)
            self._billed_before = int(prior.get("character_count") or 0)
            self._alignment_requests = int(prior.get("alignment_requests") or 0)
            self.db.update_stage_run(stage_run_id, {"status": "running", "error": None})
        else:
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
            stage_run_id = str(stage_run["id"])

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
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": output,
                    "promoted": promoted,
                    **self._usage_fields(character_count),
                    "completed_at": utc_now_iso(),
                },
            )
            return stage_run_id
        except Exception as exc:
            paused = isinstance(exc, TtsQuotaError)
            progress = self._last_progress or {}
            error = str(exc)
            resume_at: datetime | None = None
            if paused:
                resume_at = quota_resume_at(exc)
                error = quota_stop_message(
                    exc,
                    paragraphs_saved=int(progress.get("paragraphs_saved") or 0),
                    paragraphs_total=int(progress.get("paragraphs_total") or 0),
                )
                logger.warning("Narration stage run %s paused: %s", stage_run_id, error)
                fail_payload: dict[str, Any] = {
                    "status": "queued",
                    "error": None,
                    "output": {
                        **progress,
                        "summary": error,
                        "resume_at": resume_at.isoformat(),
                    },
                }
            else:
                logger.exception("Narration stage run %s failed", stage_run_id)
                fail_payload = {
                    "status": "failed",
                    "error": error,
                    "completed_at": utc_now_iso(),
                }
            try:
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
            if progress:
                fail_payload.update(
                    self._usage_fields(int(progress.get("character_count") or 0))
                )
            self.db.update_stage_run(stage_run_id, fail_payload)
            if paused and resume_at is not None:
                raise NarrationPaused(
                    error, resume_at=resume_at, stage_run_id=stage_run_id
                ) from exc
            raise

    def _stage_run_output(self, production_run_id: str, stage_run_id: str) -> dict[str, Any]:
        for row in self.db.list_stage_runs_for_production_run(production_run_id):
            if str(row.get("id")) == stage_run_id:
                output = row.get("output") or {}
                return output if isinstance(output, dict) else {}
        return {}

    def _publish_progress(
        self,
        stage_run_id: str,
        *,
        total: int,
        narrated: int,
        reused: int,
        skipped: int,
        character_count: int,
        paragraphs_total: int = 0,
        paragraphs_saved: int = 0,
    ) -> dict[str, Any]:
        output = _progress_output(
            total=total,
            narrated=narrated,
            reused=reused,
            skipped=skipped,
            character_count=character_count,
            voice_id=self.client.voice_id,
            model_id=self.client.model_id,
            paragraphs_total=paragraphs_total,
            paragraphs_saved=paragraphs_saved,
        )
        output["alignment_requests"] = self._alignment_requests
        self._last_progress = output
        self.db.update_stage_run(stage_run_id, {"output": output})
        return output

    def _ensure_timings(
        self,
        result: NarrationResult,
        text: str,
        where: str,
    ) -> NarrationResult:
        """Return `result` with the best word timings available for `text`.

        Estimated or invalid timings go through ElevenLabs forced alignment when
        a key is set. Invalid provider timings with no estimate to fall back to
        fail the stage, since the Reader would highlight the wrong words.
        """
        quality = result.alignment_quality or timing_quality(
            text,
            result.words,
            result.duration_seconds,
        )
        estimated_result = replace(result, alignment_quality=quality)
        result = estimated_result
        needs_forced_alignment = (
            result.alignment_source == "estimated" or not bool(quality.get("valid"))
        )
        elevenlabs_key = get_settings().narration.elevenlabs_api_key
        if needs_forced_alignment and elevenlabs_key:
            self._alignment_requests += 1
            try:
                aligned_words, forced_quality = force_align_audio(
                    audio=result.audio,
                    text=text,
                    api_key=elevenlabs_key,
                    content_type=getattr(self.client, "audio_content_type", "audio/mpeg"),
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
                        "Forced alignment was invalid for %s; keeping %s timings. %s",
                        where,
                        result.alignment_source,
                        forced_quality,
                    )
            except ElevenLabsError:
                logger.exception("Forced alignment failed for %s.", where)
        if result.alignment_source != "estimated" and not quality.get("valid"):
            if estimated_result.alignment_source == "estimated":
                logger.warning(
                    "Reverting to estimated alignment for %s. %s", where, quality
                )
                return estimated_result
            raise RuntimeError(
                f"Invalid {getattr(self.client, 'provider', 'TTS')} alignment "
                f"for {where}: {quality}"
            )
        return result

    def _store_paragraph_audio(
        self,
        *,
        workspace_id: str,
        source: dict[str, Any],
        source_id: str,
        chapter: dict[str, Any],
        chapter_id: str,
        clip_index: int,
        rows: list[dict[str, Any]],
        existing_rows: dict[str, dict[str, Any]],
        audio: bytes,
        words: list[WordTiming],
        duration_seconds: float,
        character_cost: int,
        alignment_source: str,
        alignment_quality: dict[str, Any],
        request_id: str | None,
    ) -> None:
        """Store one audio file shared by `rows`, with words on its timeline."""
        per_paragraph_words = assign_words_to_paragraphs(rows, words)
        audio_path = narration_paragraph_path(
            source,
            getattr(self.client, "provider", "tts"),
            self.client.model_id,
            self.client.voice_id,
            chapter_id,
            clip_index,
            str(rows[0]["id"]),
            extension=_audio_extension(self.client),
        )
        self.storage.upload(
            audio_path,
            audio,
            bucket=self.storage.sources_bucket,
            content_type=getattr(self.client, "audio_content_type", "audio/mpeg"),
        )
        for row, paragraph_words in zip(rows, per_paragraph_words, strict=True):
            text_hash = _text_hash(_paragraph_text(row))
            self.db.upsert_narration_segment(
                {
                    "workspace_id": workspace_id,
                    "source_id": source_id,
                    "chapter_id": chapter.get("id"),
                    "segment_id": row["id"],
                    "provider": getattr(self.client, "provider", "tts"),
                    "voice_id": self.client.voice_id,
                    "model_id": self.client.model_id,
                    "text_hash": text_hash,
                    "audio_path": audio_path,
                    "duration_seconds": duration_seconds,
                    "words": [word.to_dict() for word in paragraph_words],
                    "alignment_source": alignment_source,
                    "alignment_quality": alignment_quality,
                    "request_id": request_id,
                    "character_count": character_cost,
                    "updated_at": utc_now_iso(),
                }
            )
            existing_rows[str(row["id"])] = {
                "audio_path": audio_path,
                "model_id": self.client.model_id,
                "text_hash": text_hash,
            }

    def _speak_paragraphs_separately(
        self,
        *,
        workspace_id: str,
        source: dict[str, Any],
        source_id: str,
        chapter: dict[str, Any],
        chapter_id: str,
        clip_index: int,
        rows: list[dict[str, Any]],
        existing_rows: dict[str, dict[str, Any]],
        narrated: int,
        reused: int,
        refused_texts: set[str],
    ) -> int:
        """Speak `rows` one paragraph at a time after their clip was refused.

        A paragraph the provider still refuses stays missing; it is never
        replaced with silence. Text in `refused_texts` was already refused and
        is not sent again. Returns the characters billed now.
        """
        billed = 0
        for row in rows:
            text = _paragraph_text(row)
            where = (
                f"paragraph {row.get('id')} in source {source_id} chapter {chapter_id} "
                f"clip {clip_index}"
            )
            if text in refused_texts:
                logger.warning("Leaving refused %s (%d chars) missing.", where, len(text))
                continue
            try:
                result = self.client.synthesize_with_timestamps(text)
            except GeminiTtsError as exc:
                if _stops_run(exc):
                    raise
                if "missing audio inline data" not in str(exc) and not (
                    _can_skip_gemini_clip(exc, narrated=narrated, reused=reused)
                ):
                    raise
                logger.warning(
                    "Leaving %s (%d chars) missing: %s", where, len(text), exc
                )
                continue
            result = self._ensure_timings(result, text, where)
            self._store_paragraph_audio(
                workspace_id=workspace_id,
                source=source,
                source_id=source_id,
                chapter=chapter,
                chapter_id=chapter_id,
                clip_index=clip_index,
                rows=[row],
                existing_rows=existing_rows,
                audio=result.audio,
                words=result.words,
                duration_seconds=result.duration_seconds,
                character_cost=result.character_cost,
                alignment_source=result.alignment_source,
                alignment_quality=result.alignment_quality or {},
                request_id=result.request_id,
            )
            billed += result.character_cost
        return billed

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
        speakable: list[dict[str, Any]] = []
        skipped = 0
        for chapter in chapters:
            paragraph_rows = _paragraph_rows_for_chapter(chapter, segments)
            speakable.extend(
                row for row in paragraph_rows if _is_speakable(_paragraph_text(row))
            )
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
        character_count = self._billed_before
        previous_request_ids: list[str] = []

        def publish() -> dict[str, Any]:
            return self._publish_progress(
                stage_run_id,
                total=clips_total,
                narrated=narrated,
                reused=reused,
                skipped=skipped,
                character_count=character_count,
                paragraphs_total=len(speakable),
                paragraphs_saved=sum(
                    1
                    for row in speakable
                    if _saved_paragraph(row, existing_rows, self.client.model_id)
                ),
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
            saved = [
                _saved_paragraph(row, existing_rows, self.client.model_id)
                for row in clip_rows
            ]
            if clip_rows and all(saved):
                reused += 1
                previous_request_ids = []
                output = publish()
                continue

            missing_rows = [
                row
                for row, found in zip(clip_rows, saved, strict=True)
                if found is None
            ]
            text = _joined_clip_text(clip_rows)
            result = None
            if not any(saved):
                try:
                    result = self.client.synthesize_with_timestamps(
                        text,
                        previous_request_ids=previous_request_ids,
                    )
                except GeminiTtsError as exc:
                    message = str(exc)
                    if _stops_run(exc):
                        raise
                    if "missing audio inline data" in message:
                        logger.warning(
                            "Gemini returned no audio for source %s chapter %s "
                            "clip %d (%d chars). Trying its paragraphs one at a time.",
                            source_id,
                            chapter_id,
                            clip_index,
                            len(text),
                        )
                    elif not _can_skip_gemini_clip(
                        exc, narrated=narrated, reused=reused
                    ):
                        raise
                    else:
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
                        output = publish()
                        continue
            if result is None:
                spoke = self._speak_paragraphs_separately(
                    workspace_id=workspace_id,
                    source=source,
                    source_id=source_id,
                    chapter=chapter,
                    chapter_id=chapter_id,
                    clip_index=clip_index,
                    rows=missing_rows,
                    existing_rows=existing_rows,
                    narrated=narrated,
                    reused=reused,
                    refused_texts=set() if any(saved) else {text},
                )
                character_count += spoke
                if spoke:
                    narrated += 1
                elif any(
                    _saved_paragraph(row, existing_rows, self.client.model_id)
                    for row in clip_rows
                ):
                    reused += 1
                else:
                    skipped += 1
                previous_request_ids = []
                output = publish()
                continue
            result = self._ensure_timings(
                result,
                text,
                f"source {source_id} chapter {chapter_id} clip {clip_index}",
            )
            quality = result.alignment_quality
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
                existing_rows[str(row["id"])] = {
                    "audio_path": audio_path,
                    "model_id": self.client.model_id,
                    "text_hash": _text_hash(_paragraph_text(row)),
                }

            narrated += 1
            character_count += result.character_cost
            if result.request_id:
                previous_request_ids = (previous_request_ids + [result.request_id])[-3:]

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
        paragraphs_total = 0

        for chapter in chapters:
            paragraphs_total += sum(
                1
                for row in _paragraph_rows_for_chapter(chapter, segments)
                if _is_speakable(_paragraph_text(row))
            )
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

        paragraph_counts = {
            "paragraphs_total": paragraphs_total,
            "paragraphs_saved": segment_total,
            "paragraphs_missing": max(paragraphs_total - segment_total, 0),
        }
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
        previous_manifest: dict[str, Any] = {}
        if keep:
            raw_manifest = keep.get("manifest") or {}
            if isinstance(raw_manifest, dict):
                previous_manifest = raw_manifest
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
            **paragraph_counts,
            "clip_count": clip_count,
            "clips_total": resolved_clips_total,
            "total_duration_seconds": round(total_duration, 3),
            "chapters": manifest_chapters,
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        storage_path = downloadable_artifact_path(source, "narration_audio")
        db_manifest: dict[str, Any] = {
            "voice_id": self.client.voice_id,
            "model_id": self.client.model_id,
            "status": status,
            "generated_at": generated_at,
            "updated_at": now,
            "segment_count": segment_total,
            **paragraph_counts,
            "clip_count": clip_count,
            "clips_total": resolved_clips_total,
            "chapter_count": len(manifest_chapters),
            "chapter_titles": [c["title"] for c in manifest_chapters],
            "total_duration_seconds": round(total_duration, 3),
        }
        # Keep the clip-set hash so an unchanged republish can reuse book.mp3.
        # The path stays off the row until combine confirms the file.
        if complete:
            previous_hash = previous_manifest.get("combined_audio_hash")
            previous_name = previous_manifest.get("combined_audio_filename")
            if isinstance(previous_hash, str) and previous_hash:
                db_manifest["combined_audio_hash"] = previous_hash
            if isinstance(previous_name, str) and previous_name:
                db_manifest["combined_audio_filename"] = previous_name
        payload = {
            "workspace_id": workspace_id,
            "source_id": source["id"],
            "production_run_id": production_run_id,
            "artifact_type": "narration_audio",
            "format": "json",
            "filename": filename,
            "storage_path": storage_path,
            "file_size_bytes": len(manifest_bytes),
            "manifest": db_manifest,
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
