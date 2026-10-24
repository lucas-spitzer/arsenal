"""Join narration clips into one MP3 without encoder gaps between them.

Each clip is its own file, so splicing the bytes would play encoder padding and
the silence a TTS call leaves on both ends. Decoding to PCM, trimming only
those edges, and encoding once leaves a single track.
"""

from __future__ import annotations

import array
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.worker.db import WorkerDatabase
from app.worker.storage import WorkerStorage

logger = logging.getLogger(__name__)

SAME_CHAPTER_GAP_SECONDS = 0.3
CHAPTER_GAP_SECONDS = 0.9
EDGE_TRIM_CAP_SECONDS = 0.5
# About -40 dBFS for 16-bit audio. Windows quieter than this are edge silence.
SILENCE_RMS_THRESHOLD = 328
FALLBACK_SAMPLE_RATE = 44100
MP3_BITRATE = "64k"

NarrationDownloadState = Literal["ready", "preparing", "missing"]


class NarrationCombineError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrderedClip:
    audio_path: str
    chapter_sequence: int
    text_hashes: tuple[str, ...]


def ordered_clips(chapters: list[dict[str, Any]]) -> list[OrderedClip]:
    """One clip per audio file, in reading order.

    Paragraphs that share a file are one clip. Their text hashes stay in
    segment order so an edit to any of them changes the combine hash.
    """
    ordered_chapters = sorted(
        chapters,
        key=lambda chapter: int(chapter.get("sequence_index") or 0),
    )
    clips: list[OrderedClip] = []
    for chapter in ordered_chapters:
        sequence = int(chapter.get("sequence_index") or 0)
        hashes_by_path: dict[str, list[str]] = {}
        path_order: list[str] = []
        segments = sorted(
            chapter.get("segments") or [],
            key=lambda segment: int(segment.get("sequence_index") or 0),
        )
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            path = str(segment.get("audio_path") or "").strip()
            if not path:
                continue
            if path not in hashes_by_path:
                hashes_by_path[path] = []
                path_order.append(path)
            hashes_by_path[path].append(str(segment.get("text_hash") or ""))
        for path in path_order:
            clips.append(
                OrderedClip(
                    audio_path=path,
                    chapter_sequence=sequence,
                    text_hashes=tuple(hashes_by_path[path]),
                )
            )
    return clips


def clip_set_hash(clips: list[OrderedClip]) -> str:
    payload = [
        {
            "path": clip.audio_path,
            "chapter": clip.chapter_sequence,
            "hashes": list(clip.text_hashes),
        }
        for clip in clips
    ]
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def combined_audio_path(clip_path: str) -> str:
    parent, _separator, _name = clip_path.rpartition("/")
    if not parent:
        return "book.mp3"
    return f"{parent}/book.mp3"


def gap_seconds(previous: OrderedClip, following: OrderedClip) -> float:
    if previous.chapter_sequence == following.chapter_sequence:
        return SAME_CHAPTER_GAP_SECONDS
    return CHAPTER_GAP_SECONDS


def mp3_download_name(title: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in " ._-'" else " "
        for character in title
    )
    cleaned = " ".join(cleaned.split()).strip(" .")
    return f"{cleaned or 'Narration'}.mp3"


def narration_download_state(manifest: dict[str, Any]) -> NarrationDownloadState:
    status = str(manifest.get("combined_audio_status") or "")
    path = str(manifest.get("combined_audio_path") or "").strip()
    if status == "preparing":
        return "preparing"
    if path and status != "failed":
        return "ready"
    return "missing"


def narration_download_filename(manifest: dict[str, Any]) -> str:
    name = str(manifest.get("combined_audio_filename") or "").strip()
    if name.endswith(".mp3") and name != ".mp3":
        return name
    return "book.mp3"


def silence_pcm(seconds: float, sample_rate: int) -> bytes:
    count = int(round(seconds * sample_rate))
    if count <= 0:
        return b""
    return b"\x00\x00" * count


def trim_pcm_edges(pcm: bytes, sample_rate: int) -> bytes:
    """Drop quiet samples at the head and tail, up to half a second each.

    Silence inside the clip stays. That is the pause the voice already made
    between paragraphs.
    """
    if sample_rate <= 0 or len(pcm) < 4:
        return pcm
    usable = len(pcm) - (len(pcm) % 2)
    samples = array.array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    window = max(1, int(sample_rate * 0.01))
    cap = int(sample_rate * EDGE_TRIM_CAP_SECONDS)
    total = len(samples)
    if total <= window:
        return pcm[:usable]

    def quiet(start: int, end: int) -> bool:
        accumulated = 0
        for index in range(start, end):
            value = samples[index]
            accumulated += value * value
        rms = (accumulated / (end - start)) ** 0.5
        return rms < SILENCE_RMS_THRESHOLD

    start = 0
    while start + window <= total and start < cap and quiet(start, start + window):
        start += window
    end = total
    trimmed_tail = 0
    while end - window >= start and trimmed_tail < cap and quiet(end - window, end):
        end -= window
        trimmed_tail += window
    if end <= start:
        return pcm[:usable]
    trimmed = samples[start:end]
    if sys.byteorder != "little":
        trimmed.byteswap()
    return trimmed.tobytes()


def assemble_pcm(
    pieces: list[bytes],
    clips: list[OrderedClip],
    sample_rate: int,
) -> bytes:
    if len(pieces) != len(clips):
        raise NarrationCombineError("Each clip needs one PCM buffer.")
    if not pieces:
        return b""
    output = bytearray()
    for index, pcm in enumerate(pieces):
        output.extend(trim_pcm_edges(pcm, sample_rate))
        if index + 1 < len(pieces):
            output.extend(
                silence_pcm(
                    gap_seconds(clips[index], clips[index + 1]),
                    sample_rate,
                )
            )
    return bytes(output)


def target_sample_rate(rates: list[int]) -> int:
    if rates and all(rate == rates[0] and rate > 0 for rate in rates):
        return rates[0]
    return FALLBACK_SAMPLE_RATE


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _run_ffmpeg(args: list[str], *, stdin: bytes | None = None) -> bytes:
    completed = subprocess.run(
        args,
        input=stdin,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise NarrationCombineError(detail or "ffmpeg failed.")
    return completed.stdout


def probe_sample_rate(audio: bytes, suffix: str) -> int:
    with tempfile.NamedTemporaryFile(suffix=f".{suffix}") as handle:
        handle.write(audio)
        handle.flush()
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                handle.name,
            ],
            capture_output=True,
            check=False,
        )
    text = completed.stdout.decode("utf-8", errors="replace").strip()
    if text.isdigit():
        return int(text)
    return FALLBACK_SAMPLE_RATE


def decode_pcm(audio: bytes, suffix: str, sample_rate: int) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=f".{suffix}") as handle:
        handle.write(audio)
        handle.flush()
        return _run_ffmpeg(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                handle.name,
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "pipe:1",
            ]
        )


def encode_mp3(pcm: bytes, sample_rate: int) -> bytes:
    return _run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            MP3_BITRATE,
            "-f",
            "mp3",
            "pipe:1",
        ],
        stdin=pcm,
    )


def render_book_mp3(clips: list[OrderedClip], audio_for: dict[str, bytes]) -> bytes:
    if not clips:
        raise NarrationCombineError("Narration has no audio clips.")
    if not ffmpeg_available():
        raise NarrationCombineError("ffmpeg is not installed.")
    loaded: list[tuple[OrderedClip, bytes, str]] = []
    for clip in clips:
        audio = audio_for.get(clip.audio_path)
        if audio is None:
            raise NarrationCombineError(f"Missing audio for {clip.audio_path}.")
        suffix = Path(clip.audio_path).suffix.lstrip(".").lower() or "mp3"
        loaded.append((clip, audio, suffix))
    rate = target_sample_rate(
        [probe_sample_rate(audio, suffix) for _clip, audio, suffix in loaded]
    )
    pieces = [decode_pcm(audio, suffix, rate) for _clip, audio, suffix in loaded]
    pcm = assemble_pcm(pieces, [clip for clip, _audio, _suffix in loaded], rate)
    if not pcm:
        raise NarrationCombineError("Combined narration was empty.")
    return encode_mp3(pcm, rate)


def _manifest_of(artifact: dict[str, Any]) -> dict[str, Any]:
    manifest = artifact.get("manifest") or {}
    if isinstance(manifest, dict):
        return dict(manifest)
    return {}


def _write_manifest(
    db: WorkerDatabase,
    artifact_id: str,
    manifest: dict[str, Any],
) -> None:
    db.update_artifact(artifact_id, {"manifest": manifest})


def combine_narration_artifact(
    db: WorkerDatabase,
    storage: WorkerStorage,
    artifact_id: str,
) -> dict[str, Any]:
    """Build book.mp3 for a finished narration, or keep the existing file."""
    artifact = db.get_artifact(artifact_id)
    if artifact is None or artifact.get("artifact_type") != "narration_audio":
        raise NarrationCombineError("Narration artifact not found.")

    manifest = _manifest_of(artifact)
    if str(manifest.get("status") or "") == "in_progress":
        raise NarrationCombineError("Narration is still in progress.")

    document_bytes = storage.download(str(artifact["storage_path"]))
    document = json.loads(document_bytes)
    if not isinstance(document, dict):
        raise NarrationCombineError("Narration manifest was not an object.")
    chapters = document.get("chapters") or []
    if not isinstance(chapters, list):
        raise NarrationCombineError("Narration manifest has no chapters.")
    clips = ordered_clips(chapters)
    if not clips:
        raise NarrationCombineError("Narration has no audio clips.")

    digest = clip_set_hash(clips)
    path = combined_audio_path(clips[0].audio_path)
    filename = mp3_download_name(str(document.get("title") or "Narration"))
    if manifest.get("combined_audio_hash") == digest:
        manifest["combined_audio_path"] = path
        manifest["combined_audio_status"] = "ready"
        manifest["combined_audio_filename"] = filename
        manifest.pop("combined_audio_error", None)
        _write_manifest(db, artifact_id, manifest)
        return {"combined_audio_path": path, "skipped": True}

    manifest["combined_audio_status"] = "preparing"
    manifest.pop("combined_audio_path", None)
    manifest.pop("combined_audio_error", None)
    _write_manifest(db, artifact_id, manifest)

    try:
        audio_for = {
            clip.audio_path: storage.download(clip.audio_path) for clip in clips
        }
        mp3 = render_book_mp3(clips, audio_for)
        storage.upload(
            path,
            mp3,
            bucket=storage.sources_bucket,
            content_type="audio/mpeg",
        )
    except Exception as exc:
        manifest["combined_audio_status"] = "failed"
        manifest["combined_audio_error"] = str(exc)
        _write_manifest(db, artifact_id, manifest)
        raise

    manifest["combined_audio_path"] = path
    manifest["combined_audio_hash"] = digest
    manifest["combined_audio_status"] = "ready"
    manifest["combined_audio_filename"] = filename
    manifest["combined_audio_bytes"] = len(mp3)
    manifest.pop("combined_audio_error", None)
    _write_manifest(db, artifact_id, manifest)
    logger.info("Wrote combined narration %s (%d bytes)", path, len(mp3))
    return {"combined_audio_path": path, "skipped": False}
