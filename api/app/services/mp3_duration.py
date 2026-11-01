"""Audiobook length from an MP3 header.

Constant-bitrate files use the file size and the first frame's bitrate.
Variable-bitrate files use the Xing or Info frame count when it sits in
the first frame. Either way only the start of the file is required.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.repositories.artifacts import ArtifactRepository
from app.services.supabase_storage import SupabaseStorageClient, SupabaseStorageError

logger = logging.getLogger(__name__)

# MPEG version bits: 3 = MPEG1, 2 = MPEG2, 0 = MPEG2.5. 1 is reserved.
# Layer bits: 3 = Layer I, 2 = Layer II, 1 = Layer III. 0 is reserved.
_BITRATE_KBPS: dict[tuple[int, int], list[int]] = {
    (3, 3): [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, 0],
    (3, 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0],
    (3, 1): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
    (2, 3): [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, 0],
    (2, 1): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
    (0, 3): [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, 0],
    (0, 1): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
}
_BITRATE_KBPS[(2, 2)] = _BITRATE_KBPS[(2, 1)]
_BITRATE_KBPS[(0, 2)] = _BITRATE_KBPS[(0, 1)]

_SAMPLE_RATES = {
    3: (44100, 48000, 32000),
    2: (22050, 24000, 16000),
    0: (11025, 12000, 8000),
}

_HEADER_READ = 65_536
_FRAME_READ = 8_192


@dataclass(frozen=True)
class _Frame:
    version: int
    layer: int
    bitrate: int
    sample_rate: int
    channel_mode: int

    @property
    def samples_per_frame(self) -> int:
        if self.layer == 3:
            return 384
        if self.layer == 1 and self.version != 3:
            return 576
        return 1152

    @property
    def side_info_size(self) -> int:
        mono = self.channel_mode == 3
        if self.version == 3:
            return 17 if mono else 32
        return 9 if mono else 17


def id3v2_audio_offset(data: bytes) -> int:
    """Byte index where audio starts, after an ID3v2 tag when one is present."""
    if len(data) < 10 or not data.startswith(b"ID3"):
        return 0
    size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
    footer = 10 if data[5] & 0x10 else 0
    return 10 + size + footer


def mp3_duration_seconds(audio: bytes, *, file_size: int, skipped: int = 0) -> float | None:
    """Seconds of audio in `audio`, which must start at the first frame.

    `file_size` is the full object size. `skipped` is the ID3 prefix already
    removed from `audio` and excluded from the bitrate estimate.
    """
    found = _first_frame(audio)
    if found is None:
        return None
    offset, frame = found
    frames = _xing_frames(audio, offset, frame)
    if frames:
        return frames * frame.samples_per_frame / frame.sample_rate
    audio_bytes = file_size - skipped
    if audio_bytes <= 0 or frame.bitrate <= 0:
        return None
    return audio_bytes * 8 / frame.bitrate


def _first_frame(audio: bytes) -> tuple[int, _Frame] | None:
    if len(audio) < 4:
        return None
    limit = min(len(audio) - 4, 8192)
    for index in range(limit + 1):
        if audio[index] != 0xFF or (audio[index + 1] & 0xE0) != 0xE0:
            continue
        frame = _parse_header(audio[index : index + 4])
        if frame is not None:
            return index, frame
    return None


def _parse_header(header: bytes) -> _Frame | None:
    version = (header[1] >> 3) & 0x3
    layer = (header[1] >> 1) & 0x3
    bitrate_index = (header[2] >> 4) & 0xF
    sample_index = (header[2] >> 2) & 0x3
    channel_mode = (header[3] >> 6) & 0x3
    table = _BITRATE_KBPS.get((version, layer))
    rates = _SAMPLE_RATES.get(version)
    if table is None or rates is None or bitrate_index in {0, 15} or sample_index == 3:
        return None
    return _Frame(
        version=version,
        layer=layer,
        bitrate=table[bitrate_index] * 1000,
        sample_rate=rates[sample_index],
        channel_mode=channel_mode,
    )


def _xing_frames(audio: bytes, frame_offset: int, frame: _Frame) -> int | None:
    start = frame_offset + 4 + frame.side_info_size
    tag = audio[start : start + 4]
    if tag not in {b"Xing", b"Info"} or len(audio) < start + 12:
        return None
    flags = int.from_bytes(audio[start + 4 : start + 8], "big")
    if not flags & 0x1:
        return None
    count = int.from_bytes(audio[start + 8 : start + 12], "big")
    return count or None


def _stored_duration(manifest: object) -> float | None:
    if not isinstance(manifest, dict):
        return None
    seconds = manifest.get("duration_seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    if seconds <= 0:
        return None
    return float(seconds)


async def _read_prefix(
    storage: SupabaseStorageClient,
    *,
    bucket: str,
    path: str,
    start: int,
    end: int,
) -> bytes | None:
    try:
        return await storage.download_range(bucket=bucket, path=path, start=start, end=end)
    except SupabaseStorageError:
        logger.warning("Could not read audiobook header at %s", path)
        return None


async def probe_audiobook_duration(
    storage: SupabaseStorageClient,
    *,
    bucket: str,
    path: str,
    file_size: int,
) -> float | None:
    """Read the MP3 header and return the length in seconds."""
    if file_size <= 0 or not path:
        return None
    prefix = await _read_prefix(storage, bucket=bucket, path=path, start=0, end=_HEADER_READ - 1)
    if not prefix:
        return None
    offset = id3v2_audio_offset(prefix)
    if offset < 0 or offset >= file_size:
        return None
    if offset >= len(prefix):
        audio = await _read_prefix(
            storage,
            bucket=bucket,
            path=path,
            start=offset,
            end=offset + _FRAME_READ - 1,
        )
        if not audio:
            return None
        return mp3_duration_seconds(audio, file_size=file_size, skipped=offset)
    return mp3_duration_seconds(prefix[offset:], file_size=file_size, skipped=offset)


async def with_audiobook_durations(
    rows: list[dict[str, Any]],
    *,
    artifacts: ArtifactRepository,
    storage: SupabaseStorageClient,
    bucket: str,
) -> list[dict[str, Any]]:
    """Fill `duration_seconds` on audiobook rows that do not have it yet."""

    async def fill(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("artifact_type") != "audiobook" or _stored_duration(row.get("manifest")):
            return row
        path = str(row.get("storage_path") or "")
        file_size = int(row.get("file_size_bytes") or 0)
        seconds = await probe_audiobook_duration(
            storage,
            bucket=bucket,
            path=path,
            file_size=file_size,
        )
        if seconds is None or seconds <= 0:
            return row
        manifest = dict(row.get("manifest") or {})
        manifest["duration_seconds"] = round(seconds)
        try:
            await artifacts.update(str(row["id"]), {"manifest": manifest})
        except Exception:
            logger.exception("Could not store audiobook duration for %s", row.get("id"))
        return {**row, "manifest": manifest}

    return list(await asyncio.gather(*(fill(row) for row in rows)))
