from __future__ import annotations

import pytest

from app.artifact_paths import (
    audio_clip_path,
    downloadable_artifact_path,
    drafts_path,
    narration_clip_path,
    next_available_slug,
    original_path,
    pages_work_path,
    parse_work_path,
    slug_from_filename,
    storage_slug,
    work_path,
)


def _source() -> dict[str, str]:
    return {"workspace_slug": "ocs-prep", "slug": "mcdp-1-3-tactics"}


def test_storage_slug_and_filename() -> None:
    assert storage_slug("Marine Corps Doctrine") == "marine-corps-doctrine"
    assert slug_from_filename("MCDP 1-3 Tactics.pdf") == "mcdp-1-3-tactics"
    assert slug_from_filename("USMC-OCS-Knowledge-Review.md") == "usmc-ocs-knowledge-review"
    assert next_available_slug("notes", {"notes", "notes-2"}) == "notes-3"


def test_library_paths() -> None:
    source = _source()
    assert original_path("ocs-prep", "mcdp-1-3-tactics", "MCDP 1-3 Tactics.pdf") == (
        "ocs-prep/mcdp-1-3-tactics/MCDP 1-3 Tactics.pdf"
    )
    assert parse_work_path(source) == "ocs-prep/mcdp-1-3-tactics/work/parse.md"
    assert pages_work_path(source) == "ocs-prep/mcdp-1-3-tactics/work/pages.json"
    assert work_path("ocs-prep", "mcdp-1-3-tactics", "book.json") == (
        "ocs-prep/mcdp-1-3-tactics/work/book.json"
    )
    assert downloadable_artifact_path(source, "electronic_book") == (
        "ocs-prep/mcdp-1-3-tactics/book.epub"
    )
    assert downloadable_artifact_path(source, "narration_audio") == (
        "ocs-prep/mcdp-1-3-tactics/narration.json"
    )
    assert downloadable_artifact_path(source, "wiki_json") == (
        "ocs-prep/mcdp-1-3-tactics/wiki.json"
    )
    assert downloadable_artifact_path(source, "study_sheet") == (
        "ocs-prep/mcdp-1-3-tactics/sheet.pdf"
    )
    assert audio_clip_path(
        "ocs-prep",
        "mcdp-1-3-tactics",
        "speechify",
        "simba-3.2",
        "hugh_32",
        "ch-1-00.mp3",
    ) == (
        "ocs-prep/mcdp-1-3-tactics/audio/speechify/simba-3-2/hugh-32/ch-1-00.mp3"
    )
    assert drafts_path("ocs-prep", "chapter-three", "00_notes.md") == (
        "ocs-prep/drafts/chapter-three/00_notes.md"
    )
    assert narration_clip_path(
        source,
        "google",
        "gemini-3.1-flash-tts-preview",
        "Kore",
        "ch-1",
        0,
        extension="wav",
    ) == (
        "ocs-prep/mcdp-1-3-tactics/audio/google/"
        "gemini-3-1-flash-tts-preview/kore/ch-1-00.wav"
    )


def test_downloadable_artifact_path_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unknown artifact type"):
        downloadable_artifact_path(_source(), "web_explainer")
