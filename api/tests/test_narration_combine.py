import array
import shutil
import sys
import wave
from io import BytesIO

import pytest

from app.services.narration_combine import (
    CHAPTER_GAP_SECONDS,
    SAME_CHAPTER_GAP_SECONDS,
    OrderedClip,
    assemble_pcm,
    clip_set_hash,
    combined_audio_path,
    ffmpeg_available,
    mp3_download_name,
    narration_download_state,
    ordered_clips,
    render_book_mp3,
    trim_pcm_edges,
)


def _pcm(values: list[int]) -> bytes:
    samples = array.array("h", values)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def _tone(count: int, value: int = 8000) -> bytes:
    return _pcm([value] * count)


def _silence(count: int) -> bytes:
    return _pcm([0] * count)


def test_ordered_clips_share_a_file_and_keep_chapter_order() -> None:
    chapters = [
        {
            "sequence_index": 1,
            "segments": [
                {"sequence_index": 2, "audio_path": "audio/ch1-01.mp3", "text_hash": "b"},
                {"sequence_index": 0, "audio_path": "audio/ch1-00.mp3", "text_hash": "a"},
                {"sequence_index": 3, "audio_path": "audio/ch1-01.mp3", "text_hash": "c"},
            ],
        },
        {
            "sequence_index": 0,
            "segments": [
                {"sequence_index": 0, "audio_path": "audio/ch0-00.mp3", "text_hash": "z"},
            ],
        },
    ]

    clips = ordered_clips(chapters)

    assert [clip.audio_path for clip in clips] == [
        "audio/ch0-00.mp3",
        "audio/ch1-00.mp3",
        "audio/ch1-01.mp3",
    ]
    assert clips[2].text_hashes == ("b", "c")
    assert clips[2].chapter_sequence == 1
    assert combined_audio_path(clips[0].audio_path) == "audio/book.mp3"


def test_clip_hash_changes_when_a_paragraph_changes() -> None:
    first = ordered_clips(
        [{"sequence_index": 0, "segments": [{"sequence_index": 0, "audio_path": "a.mp3", "text_hash": "one"}]}]
    )
    second = ordered_clips(
        [{"sequence_index": 0, "segments": [{"sequence_index": 0, "audio_path": "a.mp3", "text_hash": "two"}]}]
    )

    assert clip_set_hash(first) != clip_set_hash(second)


def test_edge_trim_keeps_silence_inside_the_clip() -> None:
    sample_rate = 1000
    pcm = _silence(600) + _tone(200) + _silence(200) + _tone(200) + _silence(600)

    trimmed = trim_pcm_edges(pcm, sample_rate)

    assert len(trimmed) == 800 * 2
    samples = array.array("h")
    samples.frombytes(trimmed)
    if sys.byteorder != "little":
        samples.byteswap()
    assert samples[100:300] == array.array("h", [8000] * 200)
    assert samples[300:500] == array.array("h", [0] * 200)


def test_gaps_are_short_inside_a_chapter_and_longer_between_chapters() -> None:
    sample_rate = 1000
    same = [
        OrderedClip("a.mp3", 0, ("a",)),
        OrderedClip("b.mp3", 0, ("b",)),
    ]
    crossed = [
        OrderedClip("a.mp3", 0, ("a",)),
        OrderedClip("c.mp3", 1, ("c",)),
    ]
    tone = _tone(100)

    same_pcm = assemble_pcm([tone, tone], same, sample_rate)
    crossed_pcm = assemble_pcm([tone, tone], crossed, sample_rate)

    same_gap = int(SAME_CHAPTER_GAP_SECONDS * sample_rate)
    chapter_gap = int(CHAPTER_GAP_SECONDS * sample_rate)
    assert len(same_pcm) == (100 + same_gap + 100) * 2
    assert len(crossed_pcm) == (100 + chapter_gap + 100) * 2


def test_download_state_and_filename() -> None:
    assert narration_download_state({}) == "missing"
    assert narration_download_state({"combined_audio_status": "preparing"}) == "preparing"
    assert (
        narration_download_state(
            {"combined_audio_status": "failed", "combined_audio_path": "audio/book.mp3"}
        )
        == "missing"
    )
    assert (
        narration_download_state({"combined_audio_path": "audio/book.mp3"})
        == "ready"
    )
    assert mp3_download_name("Warfighting / MCDP 1") == "Warfighting MCDP 1.mp3"


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed")
def test_render_joins_wav_clips_into_one_mp3() -> None:
    def wav(samples: list[int]) -> bytes:
        buffer = BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(_pcm(samples))
        return buffer.getvalue()

    clips = [
        OrderedClip("ch0.wav", 0, ("a",)),
        OrderedClip("ch1.wav", 1, ("b",)),
    ]
    mp3 = render_book_mp3(
        clips,
        {
            "ch0.wav": wav([4000] * 8000),
            "ch1.wav": wav([4000] * 8000),
        },
    )

    assert len(mp3) > 1000
    assert shutil.which("ffprobe")
