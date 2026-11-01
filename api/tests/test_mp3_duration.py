import asyncio

from app.services.mp3_duration import (
    id3v2_audio_offset,
    mp3_duration_seconds,
    with_audiobook_durations,
)

# MPEG1 Layer III, 128 kbps, 44.1 kHz, stereo.
_FRAME = bytes([0xFF, 0xFB, 0x90, 0x00])


def _xing(frame_count: int) -> bytes:
    side_info = b"\x00" * 32
    flags = (1).to_bytes(4, "big")
    frames = frame_count.to_bytes(4, "big")
    return _FRAME + side_info + b"Xing" + flags + frames


def test_constant_bitrate_duration_uses_file_size() -> None:
    file_size = 128_000 * 65 // 8
    seconds = mp3_duration_seconds(_FRAME, file_size=file_size)
    assert seconds == 65


def test_id3_tag_is_excluded_from_the_length() -> None:
    tag = b"ID3" + b"\x00" * 7
    assert id3v2_audio_offset(tag) == 10
    audio_bytes = 128_000 * 65 // 8
    seconds = mp3_duration_seconds(_FRAME, file_size=len(tag) + audio_bytes, skipped=10)
    assert seconds == 65


def test_xing_frame_count_sets_the_length() -> None:
    frames = 1_665_234
    seconds = mp3_duration_seconds(_xing(frames), file_size=999_999)
    assert seconds is not None
    assert round(seconds) == 43_500


def test_library_rows_gain_a_stored_duration() -> None:
    file_size = 128_000 * (12 * 3600 + 5 * 60) // 8
    audio = _FRAME + b"\x00" * 64

    class Storage:
        async def download_range(self, *, bucket: str, path: str, start: int, end: int) -> bytes:
            assert bucket == "sources"
            assert path == "acme/book/audiobooks/book.mp3"
            assert start == 0
            return audio

    class Artifacts:
        def __init__(self) -> None:
            self.updated: list[dict[str, object]] = []

        async def update(self, artifact_id: str, payload: dict[str, object]) -> dict[str, object]:
            self.updated.append({"id": artifact_id, **payload})
            return payload

    artifacts = Artifacts()
    rows = asyncio.run(
        with_audiobook_durations(
            [
                {
                    "id": "art-1",
                    "artifact_type": "audiobook",
                    "storage_path": "acme/book/audiobooks/book.mp3",
                    "file_size_bytes": file_size,
                    "manifest": {"title": "Warfighting", "status": "ready"},
                },
                {
                    "id": "art-2",
                    "artifact_type": "electronic_book",
                    "manifest": {},
                },
            ],
            artifacts=artifacts,  # type: ignore[arg-type]
            storage=Storage(),  # type: ignore[arg-type]
            bucket="sources",
        ),
    )

    assert rows[0]["manifest"]["duration_seconds"] == 12 * 3600 + 5 * 60
    assert rows[1]["manifest"] == {}
    assert artifacts.updated[0]["id"] == "art-1"


def test_known_duration_is_left_alone() -> None:
    class Storage:
        async def download_range(self, **_: object) -> bytes:
            raise AssertionError("duration was already stored")

    class Artifacts:
        async def update(self, artifact_id: str, payload: dict[str, object]) -> dict[str, object]:
            raise AssertionError(artifact_id)

    rows = asyncio.run(
        with_audiobook_durations(
            [
                {
                    "id": "art-1",
                    "artifact_type": "audiobook",
                    "storage_path": "book.mp3",
                    "file_size_bytes": 10,
                    "manifest": {"duration_seconds": 90},
                }
            ],
            artifacts=Artifacts(),  # type: ignore[arg-type]
            storage=Storage(),  # type: ignore[arg-type]
            bucket="sources",
        ),
    )
    assert rows[0]["manifest"]["duration_seconds"] == 90
