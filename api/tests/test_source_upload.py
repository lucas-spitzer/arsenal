from pathlib import Path

import pytest

from app.services.source_upload import (
    SourceUploadValidationError,
    sanitize_upload_filename,
    validate_source_upload,
    validate_structured_data_upload,
)

PDF_BYTES = b"%PDF-1.4 minimal"


def test_sanitize_upload_filename_strips_directory_components() -> None:
    assert sanitize_upload_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_upload_filename("folder/report.pdf") == "report.pdf"


def test_sanitize_upload_filename_rejects_empty_name() -> None:
    with pytest.raises(SourceUploadValidationError):
        sanitize_upload_filename("../")


def test_validate_source_upload_accepts_pdf() -> None:
    filename, mime_type = validate_source_upload(
        filename="report.pdf",
        content_type="application/pdf",
        content=PDF_BYTES,
        max_bytes=1024,
    )

    assert filename == "report.pdf"
    assert mime_type == "application/pdf"


def test_validate_source_upload_accepts_markdown() -> None:
    filename, mime_type = validate_source_upload(
        filename="notes.md",
        content_type="text/markdown",
        content=b"# Orders\n",
        max_bytes=1024,
    )
    assert filename == "notes.md"
    assert mime_type == "text/markdown"


def test_validate_source_upload_rejects_non_pdf_content() -> None:
    with pytest.raises(SourceUploadValidationError, match="not a valid PDF"):
        validate_source_upload(
            filename="report.pdf",
            content_type="application/pdf",
            content=b"not-a-pdf",
            max_bytes=1024,
        )


def test_validate_source_upload_rejects_oversized_file() -> None:
    with pytest.raises(SourceUploadValidationError, match="exceeds the"):
        validate_source_upload(
            filename="report.pdf",
            content_type="application/pdf",
            content=PDF_BYTES,
            max_bytes=4,
        )


FIXTURE = Path(__file__).parent / "fixtures" / "warfighting-chapter-1.json"


def test_validate_structured_data_upload_accepts_notes_fixture() -> None:
    filename, mime_type = validate_structured_data_upload(
        filename="warfighting-chapter-1.json",
        content=FIXTURE.read_bytes(),
        max_bytes=1024 * 1024,
    )

    assert filename == "warfighting-chapter-1.json"
    assert mime_type == "application/json"


def test_validate_structured_data_upload_rejects_non_json_file() -> None:
    with pytest.raises(SourceUploadValidationError, match=r"\.json"):
        validate_structured_data_upload(filename="notes.md", content=b"# Notes", max_bytes=1024)


def test_validate_structured_data_upload_rejects_bad_json() -> None:
    with pytest.raises(SourceUploadValidationError, match="JSON"):
        validate_structured_data_upload(filename="notes.json", content=b"{nope", max_bytes=1024)


def test_validate_structured_data_upload_rejects_unusable_shape() -> None:
    with pytest.raises(SourceUploadValidationError):
        validate_structured_data_upload(filename="notes.json", content=b'{"hello":"world"}', max_bytes=1024)
