from __future__ import annotations

from typing import Any

# Bumped when classify / structure-body semantics change so already-ingested
# sources re-run normalize→chunk without re-parsing or re-researching.
CURRENT_STRUCTURE_VERSION = "1.5"


def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
    metadata = source.get("source_metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def source_parse_complete(source: dict[str, Any]) -> bool:
    parse_meta = _source_metadata(source).get("parse")
    return isinstance(parse_meta, dict) and bool(parse_meta.get("parsed_at"))


def source_research_complete(source: dict[str, Any]) -> bool:
    research = _source_metadata(source).get("research")
    return isinstance(research, dict) and bool(research.get("researched_at"))


def source_web_enrichment_complete(source: dict[str, Any]) -> bool:
    # Deliberately NOT part of source_intellex_complete: enrichment only needs
    # the research block, so already-ingested sources get backfilled without
    # re-running parse/structure/chunk.
    enrichment = _source_metadata(source).get("web_enrichment")
    return isinstance(enrichment, dict) and bool(enrichment.get("enriched_at"))


def source_normalize_complete(source: dict[str, Any]) -> bool:
    normalize = _source_metadata(source).get("normalize")
    return isinstance(normalize, dict) and bool(normalize.get("normalized_at"))


def source_trim_complete(source: dict[str, Any]) -> bool:
    trim = _source_metadata(source).get("trim")
    return isinstance(trim, dict) and bool(trim.get("trimmed_at"))


def source_structure_complete(source: dict[str, Any]) -> bool:
    """Return whether structure output matches the current structure logic.

    A missing or outdated `structure.stage_version` means the source must
    restructure even if chapters or a prior stage run already exist.
    """
    structure = _source_metadata(source).get("structure")
    if not isinstance(structure, dict):
        return False
    if not (structure.get("structured_at") and structure.get("chapter_count", 0) > 0):
        return False
    return structure.get("stage_version") == CURRENT_STRUCTURE_VERSION


def source_validate_complete(source: dict[str, Any]) -> bool:
    validate = _source_metadata(source).get("validate")
    return isinstance(validate, dict) and bool(validate.get("validated_at"))


def source_chunk_complete(source: dict[str, Any], *, has_segments: bool) -> bool:
    if not has_segments:
        return False

    parse_meta = _source_metadata(source).get("parse")
    return isinstance(parse_meta, dict) and bool(parse_meta.get("chunked_at"))


def source_intellex_complete(source: dict[str, Any], *, has_segments: bool) -> bool:
    """A source is intellex-complete once the structure-based ingest has fully run.

    Knowledge extraction is no longer part of ingest — wiki entries are curated
    manually afterwards — so ingest completeness ends at chunked segments and
    persisted chapters.
    """
    return (
        bool(source.get("storage_path"))
        and source_parse_complete(source)
        and source_research_complete(source)
        and source_normalize_complete(source)
        and source_trim_complete(source)
        and source_structure_complete(source)
        and source_validate_complete(source)
        and source_chunk_complete(source, has_segments=has_segments)
    )
