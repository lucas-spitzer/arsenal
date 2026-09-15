import pytest

from app.mathesys.stages.wiki_export import build_wiki_export


def _entry(
    entry_id: str,
    label: str,
    *,
    status: str = "canonical",
    entry_kind: str = "concept",
    evidence: list[dict] | None = None,
    origin: dict | None = None,
    prerequisites: list[str] | None = None,
) -> dict:
    return {
        "id": entry_id,
        "preferred_label": label,
        "canonical_slug": label.lower().replace(" ", "-"),
        "definition": f"Definition of {label}",
        "pronunciation": None,
        "aliases": [],
        "prerequisites": prerequisites or [],
        "importance": "supporting",
        "entry_kind": entry_kind,
        "status": status,
        "evidence": evidence or [],
        "origin": origin or {},
    }


def test_export_selects_source_and_workspace_scoped_entries() -> None:
    entries = [
        # Evidence cites the source → included, scope source.
        _entry(
            "w1",
            "Enemy System",
            evidence=[{"source_id": "src-1", "segment_id": "seg-1", "page": 3}],
        ),
        # Manual batch recorded the source in origin → included, scope source.
        _entry("w2", "Tempo", origin={"kind": "manual", "source_id": "src-1"}),
        # No source affiliation anywhere → workspace-level knowledge, included.
        _entry("w3", "OODA Loop", origin={"kind": "manual"}),
        # Affiliated with a different source → excluded.
        _entry(
            "w4",
            "Other Book Term",
            evidence=[{"source_id": "src-2", "segment_id": "seg-9", "page": 1}],
        ),
        # Deprecated → excluded regardless of affiliation.
        _entry(
            "w5",
            "Old Term",
            status="deprecated",
            evidence=[{"source_id": "src-1", "segment_id": "seg-2", "page": 4}],
        ),
    ]

    export = build_wiki_export(
        wiki_entries=entries,
        workspace_id="ws-1",
        source_id="src-1",
        source_filename="warfighting.pdf",
    )

    labels = {item["preferred_label"] for item in export["entries"]}
    assert labels == {"Enemy System", "Tempo", "OODA Loop"}
    assert export["entry_count"] == 3
    assert export["scope_counts"] == {"source": 2, "workspace": 1}
    assert export["arsenal_wiki_export"] == "1.0"


def test_export_resolves_prerequisites_to_labels() -> None:
    entries = [
        _entry(
            "w1",
            "Enemy System",
            evidence=[{"source_id": "src-1", "segment_id": "seg-1", "page": 3}],
        ),
        _entry(
            "w2",
            "Center of Gravity",
            evidence=[{"source_id": "src-1", "segment_id": "seg-2", "page": 5}],
            prerequisites=["w1"],
        ),
    ]

    export = build_wiki_export(
        wiki_entries=entries,
        workspace_id="ws-1",
        source_id="src-1",
        source_filename=None,
    )

    cog = next(
        item
        for item in export["entries"]
        if item["preferred_label"] == "Center of Gravity"
    )
    assert cog["prerequisites"] == ["Enemy System"]


def test_export_raises_when_nothing_to_export() -> None:
    with pytest.raises(RuntimeError, match="Wiki Knowledge"):
        build_wiki_export(
            wiki_entries=[
                _entry(
                    "w1",
                    "Other Book Term",
                    evidence=[{"source_id": "src-2", "segment_id": "seg-9", "page": 1}],
                ),
            ],
            workspace_id="ws-1",
            source_id="src-1",
            source_filename=None,
        )


def test_export_counts_entry_kinds() -> None:
    entries = [
        _entry("w1", "Alpha", entry_kind="term", origin={"kind": "manual", "source_id": "s"}),
        _entry("w2", "Beta", entry_kind="term", origin={"kind": "manual", "source_id": "s"}),
        _entry("w3", "Gamma", entry_kind="insight", origin={"kind": "manual", "source_id": "s"}),
    ]

    export = build_wiki_export(
        wiki_entries=entries,
        workspace_id="ws-1",
        source_id="s",
        source_filename=None,
    )

    assert export["entry_kind_counts"] == {"term": 2, "insight": 1}
