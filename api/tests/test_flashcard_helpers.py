from types import SimpleNamespace

from app.qngen.skills.flashcards.helpers import ensure_list_flashcards, prefer_term_definition


def _card(*, wiki_id: str, front: str, subtype: str = "term_definition", **extra) -> dict:
    return {
        "item_id": f"item-{wiki_id}-{front}",
        "type": "flashcard",
        "subtype": subtype,
        "wiki_ids_cited": [wiki_id],
        "front": front,
        "back": extra.get("back", f"Definition of {front}."),
        "source_chunk_ids": extra.get("source_chunk_ids", ["seg-1"]),
    }


def test_dedup_collapses_case_variant_terms() -> None:
    # Two canonical entries differing only in casing escaped wiki dedup before.
    items = [
        _card(wiki_id="wiki-1", front="Enemy system"),
        _card(wiki_id="wiki-2", front="enemy system"),
    ]

    result = prefer_term_definition(items)

    assert len(result) == 1
    assert result[0]["front"] == "Enemy system"


def test_dedup_keeps_best_grounded_card_on_collision() -> None:
    sparse = _card(wiki_id="wiki-1", front="Tempo", source_chunk_ids=["seg-1"])
    grounded = _card(
        wiki_id="wiki-2",
        front="tempo",
        source_chunk_ids=["seg-1", "seg-2", "seg-3"],
    )

    result = prefer_term_definition([sparse, grounded])

    assert len(result) == 1
    assert result[0]["front"] == "tempo"


def test_dedup_still_collapses_by_wiki_id() -> None:
    items = [
        _card(wiki_id="wiki-1", front="Tempo"),
        _card(wiki_id="wiki-1", front="What is tempo?", subtype="basic"),
    ]

    result = prefer_term_definition(items)

    assert len(result) == 1
    assert result[0]["subtype"] == "term_definition"


def test_list_item_cards_stay_beside_the_membership_card() -> None:
    items = [
        _card(wiki_id="wiki-list", front="Forms of Friction", subtype="list"),
        _card(wiki_id="wiki-list", front="Mental Friction", subtype="list_item"),
    ]

    result = prefer_term_definition(items)

    assert {card["front"] for card in result} == {"Forms of Friction", "Mental Friction"}


def test_ensure_list_flashcards_adds_missing_components() -> None:
    concept = SimpleNamespace(
        wiki_id="wiki-list",
        preferred_label="Forms of Friction",
        definition="Sources of resistance.",
        entry_kind="list",
        significance=None,
        items=[{"name": "Mental Friction", "details": "Indecision."}],
        evidence_segment_ids=["seg-1"],
    )

    result = ensure_list_flashcards([], [concept])

    assert {card["front"] for card in result} == {"Forms of Friction", "Mental Friction"}
    assert result[1]["subtype"] == "list_item"
    assert result[1]["back"] == "Indecision."


def test_dedup_keeps_distinct_terms() -> None:
    items = [
        _card(wiki_id="wiki-1", front="Tempo"),
        _card(wiki_id="wiki-2", front="Surprise"),
    ]

    result = prefer_term_definition(items)

    assert {card["front"] for card in result} == {"Tempo", "Surprise"}
