import pytest

from app.services.source_reference import ReferenceSourceError, reference_source_row
from app.worker.pipeline_runner import source_uses_intellex


def _row(**overrides: object) -> dict:
    payload = {
        "source_id": "src-1",
        "workspace_id": "ws-1",
        "owner_id": "user-1",
        "name": "MCDP 1 Warfighting",
        "background": "Doctrine for maneuver warfare.",
        "document_type": "Doctrinal publication",
        "issuing_authority": "US Marine Corps",
        "taken_slugs": set(),
    }
    payload.update(overrides)
    return reference_source_row(**payload)  # type: ignore[arg-type]


def test_reference_source_row_has_no_file() -> None:
    row = _row()

    assert row["status"] == "awaiting_file"
    assert row["source_kind"] == "document"
    assert row["mime_type"] == "application/x-pending"
    assert row["storage_path"] == ""
    assert row["file_size_bytes"] == 0
    assert row["file_hash"] == "pending:src-1"
    assert row["slug"] == "mcdp-1-warfighting"
    assert row["source_metadata"] == {
        "display_name": "MCDP 1 Warfighting",
        "background": "Doctrine for maneuver warfare.",
        "document_type": "Doctrinal publication",
        "issuing_authority": "US Marine Corps",
    }
    assert source_uses_intellex(row) is False


def test_reference_source_row_omits_blank_optional_fields() -> None:
    row = _row(background="  ", document_type=None, issuing_authority="")

    assert row["source_metadata"] == {"display_name": "MCDP 1 Warfighting"}


def test_reference_source_row_avoids_a_taken_slug() -> None:
    row = _row(taken_slugs={"mcdp-1-warfighting"})

    assert row["slug"] == "mcdp-1-warfighting-2"


def test_reference_source_filename_does_not_look_like_a_pdf() -> None:
    row = _row(name="Warfighting.pdf", background=None, document_type=None, issuing_authority=None)

    assert row["filename"] == "Warfighting"
    assert row["source_metadata"]["display_name"] == "Warfighting.pdf"
    assert source_uses_intellex(row) is False


def test_reference_source_row_requires_a_name() -> None:
    with pytest.raises(ReferenceSourceError, match="Name is required"):
        _row(name="   ")
