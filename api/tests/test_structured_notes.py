import json
from pathlib import Path

from app.intellex.wiki_candidates import WikiCandidate, promote_candidates
from app.knowledge.structured_notes import parse_structured_notes

FIXTURE = Path(__file__).parent / "fixtures" / "warfighting-chapter-1.json"


def test_warfighting_notes_become_terms_and_lists() -> None:
    notes = parse_structured_notes(FIXTURE.read_text())
    assert notes is not None

    terms = [entry for entry in notes.entries if entry["entry_kind"] == "term"]
    lists = [entry for entry in notes.entries if entry["entry_kind"] == "list"]
    assert len(terms) == 26
    assert len(lists) == 5

    friction = next(entry for entry in terms if entry["label"] == "Friction")
    assert friction["definition"].startswith("The collective force that resists all action")
    assert friction["significance"]
    assert friction["category"] == "Characteristics of War"

    characteristics = next(entry for entry in lists if entry["label"] == "Essential Characteristics of War")
    friction_item = next(item for item in characteristics["items"] if item["name"] == "Friction")
    assert friction_item["details"] != friction["definition"]
    assert characteristics["definition"].startswith("The fundamental environmental attributes")

    human_will = next(entry for entry in terms if entry["label"] == "Human Will")
    assert human_will["definition"].startswith("The central driving force")


def test_list_item_details_do_not_replace_the_term_definition() -> None:
    notes = parse_structured_notes(FIXTURE.read_text())
    assert notes is not None
    candidates = [
        WikiCandidate(
            label=entry["label"],
            definition=entry["definition"],
            entry_kind=entry["entry_kind"],
            significance=entry["significance"],
            category=entry["category"],
            items=entry["items"],
        )
        for entry in notes.entries
        if entry["label"] in {"Friction", "Essential Characteristics of War"}
    ]

    inserts, updates, conflicted = promote_candidates(
        workspace_id="ws-1",
        candidates=candidates,
        existing_entries=[],
    )

    assert updates == []
    assert conflicted == []
    by_label = {row["preferred_label"]: row for row in inserts}
    assert by_label["Friction"]["definition"].startswith("The collective force that resists all action")
    assert by_label["Essential Characteristics of War"]["entry_kind"] == "list"
    assert by_label["Essential Characteristics of War"]["canonical_slug"] == "essential-characteristics-of-war"


def test_entries_array_still_imports() -> None:
    raw = json.dumps(
        [
            {
                "label": "Tempo",
                "definition": "The rate of operations.",
                "entry_kind": "concept",
                "significance": "A competitive dynamic.",
            },
        ],
    )
    notes = parse_structured_notes(raw)
    assert notes is not None
    assert notes.entries[0]["entry_kind"] == "term"
    assert notes.entries[0]["significance"] == "A competitive dynamic."
