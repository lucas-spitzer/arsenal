import io
import json
import zipfile

import pytest

from app.knowledge.uploads import KnowledgeUploadError, UploadedPart, resolve_knowledge_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
NOTES = json.dumps(
    {
        "questions": [
            {
                "question": "What does the picture show?",
                "correct": ["A column"],
                "distractors": ["A line"],
                "image": "figure.png",
            },
        ],
    },
).encode()
MAX_BYTES = 1024 * 1024


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _part(filename: str, content: bytes, content_type: str | None = None) -> UploadedPart:
    return UploadedPart(filename=filename, content_type=content_type, content=content)


def test_zip_keeps_one_json_and_images_by_base_name() -> None:
    resolved = resolve_knowledge_upload(
        [_part("pack.zip", _zip({
            "notes/questions.json": NOTES,
            "images/figure.png": PNG,
            "__MACOSX/images/._figure.png": b"junk",
            ".DS_Store": b"store",
        }))],
        max_bytes=MAX_BYTES,
    )

    assert resolved.filename == "questions.json"
    assert resolved.content == NOTES
    assert resolved.images == {"figure.png": PNG}


def test_zip_without_json_is_rejected() -> None:
    with pytest.raises(KnowledgeUploadError, match="one JSON"):
        resolve_knowledge_upload(
            [_part("pack.zip", _zip({"images/figure.png": PNG}))],
            max_bytes=MAX_BYTES,
        )


def test_zip_rejects_a_duplicated_image_name() -> None:
    with pytest.raises(KnowledgeUploadError, match="more than once"):
        resolve_knowledge_upload(
            [_part("pack.zip", _zip({
                "questions.json": NOTES,
                "images/figure.png": PNG,
                "other/figure.png": PNG,
            }))],
            max_bytes=MAX_BYTES,
        )


def test_zip_rejects_a_path_that_escapes() -> None:
    with pytest.raises(KnowledgeUploadError, match="not a safe file name"):
        resolve_knowledge_upload(
            [_part("pack.zip", _zip({
                "questions.json": NOTES,
                "../figure.png": PNG,
            }))],
            max_bytes=MAX_BYTES,
        )


def test_json_and_image_files_selected_together() -> None:
    resolved = resolve_knowledge_upload(
        [
            _part("questions.json", NOTES, "application/json"),
            _part("figure.png", PNG, "image/png"),
        ],
        max_bytes=MAX_BYTES,
    )

    assert resolved.filename == "questions.json"
    assert resolved.content == NOTES
    assert resolved.images == {"figure.png": PNG}


def test_twenty_five_images_fit_and_twenty_six_do_not() -> None:
    images = [_part(f"figure-{index}.png", PNG, "image/png") for index in range(26)]
    resolved = resolve_knowledge_upload(
        [_part("questions.json", NOTES, "application/json"), *images[:25]],
        max_bytes=MAX_BYTES,
    )
    assert len(resolved.images) == 25

    with pytest.raises(KnowledgeUploadError, match="at most 25 images"):
        resolve_knowledge_upload(
            [_part("questions.json", NOTES, "application/json"), *images],
            max_bytes=MAX_BYTES,
        )
    with pytest.raises(KnowledgeUploadError, match="at most 25 images"):
        resolve_knowledge_upload(
            [_part("pack.zip", _zip({"questions.json": NOTES, **{f"figure-{i}.png": PNG for i in range(26)}}))],
            max_bytes=MAX_BYTES,
        )


def test_a_zip_mixed_with_other_files_is_rejected() -> None:
    with pytest.raises(KnowledgeUploadError, match="zip by itself"):
        resolve_knowledge_upload(
            [
                _part("pack.zip", _zip({"questions.json": NOTES})),
                _part("figure.png", PNG),
            ],
            max_bytes=MAX_BYTES,
        )


def test_one_notes_file_has_no_images() -> None:
    resolved = resolve_knowledge_upload(
        [_part("notes.md", b"# Notes\n", "text/markdown")],
        max_bytes=MAX_BYTES,
    )

    assert resolved.filename == "notes.md"
    assert resolved.content == b"# Notes\n"
    assert resolved.images == {}
