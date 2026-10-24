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
    assert len(terms) == 23
    assert len(lists) == 5

    friction = next(entry for entry in terms if entry["label"] == "Friction")
    assert friction["definition"].startswith("The collective force that resists all action")
    assert friction["significance"]
    assert friction["category"] == "Characteristics of War"

    characteristics = next(entry for entry in lists if entry["label"] == "Essential Characteristics of War")
    friction_item = next(item for item in characteristics["items"] if item["name"] == "Friction")
    assert friction_item["details"] != friction["definition"]
    assert characteristics["definition"].startswith("The fundamental environmental attributes")

    assert all(entry["label"] != "Human Will" for entry in terms)
    human_factors = next(entry for entry in lists if entry["label"] == "Human Factors in Combat")
    human_will = next(item for item in human_factors["items"] if item["name"] == "Human Will")
    assert human_will["details"].startswith("The central driving force")


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


def test_chapter_elos_stay_a_separate_kind() -> None:
    commission = "Explain the moral and professional obligations reposed in a USMC officer by the Commission."
    oath = "Explain the relationship between the Officer Oath, public trust, and the concept of unlimited liability."
    trust = "Identify the Marine Corps doctrine on Special Trust and Confidence and the officer's obligation under Paragraph 1100."
    notes = parse_structured_notes(
        json.dumps(
            {
                "metadata": {"document_title": "The Armed Forces Officer - Chapter 1"},
                "elos": [
                    {"elo": commission, "response": "A commission is a grant of authority."},
                    {"elo": oath, "response": "The oath commits the officer to unlimited liability."},
                    {"elo": trust, "response": "Paragraph 1100 defines special trust."},
                ],
                "terms": [
                    {
                        "term": "Special Trust and Confidence",
                        "elo_reference": commission,
                        "definition": "The presumption of character that underwrites command.",
                    },
                ],
                "key_lists": [
                    {
                        "concept": "The Four Commissioning Virtues",
                        "elo_reference": commission,
                        "overview": "The qualities attested in every commission.",
                        "items": [{"name": "Patriotism", "details": "Devotion to the nation."}],
                    },
                ],
            },
        ),
    )
    assert notes is not None

    elos = [entry for entry in notes.entries if entry["entry_kind"] == "elo"]
    terms = [entry for entry in notes.entries if entry["entry_kind"] == "term"]
    lists = [entry for entry in notes.entries if entry["entry_kind"] == "list"]
    assert [entry["label"] for entry in elos] == [commission, oath, trust]
    assert [entry["elo_index"] for entry in elos] == [0, 1, 2]
    assert elos[0]["definition"] == "A commission is a grant of authority."
    assert terms[0]["elo_reference"] == commission
    assert lists[0]["elo_reference"] == commission

    candidates = [
        WikiCandidate(
            label=entry["label"],
            definition=entry["definition"],
            entry_kind=entry["entry_kind"],
        )
        for entry in notes.entries
    ]
    inserts, updates, conflicted = promote_candidates(
        workspace_id="ws-1",
        candidates=candidates,
        existing_entries=[],
    )
    assert updates == []
    assert conflicted == []
    promoted = {row["preferred_label"]: row for row in inserts}
    assert promoted[commission]["entry_kind"] == "elo"
    assert promoted["Special Trust and Confidence"]["entry_kind"] == "term"
    assert promoted["The Four Commissioning Virtues"]["entry_kind"] == "list"
