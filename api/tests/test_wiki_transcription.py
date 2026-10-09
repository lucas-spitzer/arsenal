from __future__ import annotations

import pytest

from app.services.wiki_transcription import (
    FILE_SEPARATOR,
    WikiTranscriptionError,
    concatenate_transcriptions,
    decode_text_attachment,
    resolve_attachment_mime_type,
    transcribe_attachment_content,
    validate_note_attachment,
)


def test_resolve_markdown_as_text() -> None:
    mime, is_text = resolve_attachment_mime_type(
        filename="notes.md",
        content_type="text/markdown",
    )
    assert is_text is True
    assert "markdown" in mime or mime == "text/plain"


def test_resolve_image_as_binary() -> None:
    mime, is_text = resolve_attachment_mime_type(
        filename="scan.HEIC",
        content_type="image/heic",
    )
    assert is_text is False
    assert mime == "image/heic"


def test_json_is_not_a_note_attachment() -> None:
    with pytest.raises(WikiTranscriptionError, match="structured data source"):
        resolve_attachment_mime_type(
            filename="entries.json",
            content_type="application/json",
        )


def test_validate_note_attachment_rejects_json() -> None:
    with pytest.raises(WikiTranscriptionError, match="structured data source"):
        validate_note_attachment(
            order=0,
            filename="entries.json",
            content_type="application/json",
            content=b'{"entries":[{"label":"Tempo","definition":"The rate of operations."}]}',
            max_bytes=10_000,
        )


def test_reject_unsupported_extension() -> None:
    with pytest.raises(WikiTranscriptionError, match="Unsupported"):
        resolve_attachment_mime_type(filename="notes.xlsx", content_type=None)


def test_validate_note_attachment_size_cap() -> None:
    with pytest.raises(WikiTranscriptionError, match="exceeds"):
        validate_note_attachment(
            order=0,
            filename="big.md",
            content_type="text/markdown",
            content=b"x" * 100,
            max_bytes=50,
        )


def test_decode_and_concat_text_files() -> None:
    first = decode_text_attachment("Enemy system — parts".encode(), filename="a.md")
    second = decode_text_attachment(b"insight: tempo", filename="b.txt")
    combined = concatenate_transcriptions([first, second])
    assert combined == f"Enemy system — parts{FILE_SEPARATOR}insight: tempo"


def test_transcribe_text_attachment_passthrough() -> None:
    attachment = validate_note_attachment(
        order=0,
        filename="notes.md",
        content_type="text/markdown",
        content=b"# Center of gravity\n\nThe hub of power.",
        max_bytes=10_000,
    )
    text = transcribe_attachment_content(attachment, attachment.content)
    assert "Center of gravity" in text
    assert "hub of power" in text


def test_multi_file_order_preserved() -> None:
    from app.services.wiki_transcription import transcribe_attachments_in_order

    items = [
        (
            {
                "order": 1,
                "filename": "b.md",
                "mime_type": "text/markdown",
            },
            b"second page",
        ),
        (
            {
                "order": 0,
                "filename": "a.md",
                "mime_type": "text/markdown",
            },
            b"first page",
        ),
    ]
    combined = transcribe_attachments_in_order(items)
    assert combined.startswith("first page")
    assert "second page" in combined
    assert FILE_SEPARATOR in combined
