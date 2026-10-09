# Flashcard skill helpers — deterministic post-processing hooks.

from __future__ import annotations

from typing import Any


def prefer_term_definition(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate flashcards down to one card per concept and per term.

    Two layers of dedup:

    1. By citing ``wiki_id`` — at most one card per canonical concept.
    2. By case-folded term front — collapses near-duplicate ``term_definition``
       cards that escaped the wiki dedup because canonicalization produced two
       entries differing only in casing (e.g. ``Enemy system`` vs
       ``enemy system``).

    Within a collision the best-grounded ``term_definition`` card wins: cards are
    ordered so ``term_definition`` comes first, then by citation count, then by
    definition length.
    """
    seen_wiki: set[str] = set()
    seen_front: set[str] = set()
    result: list[dict[str, Any]] = []

    for item in sorted(items, key=_dedup_rank):
        # A list may contribute one card per member. Those cite the list, so
        # they must not collapse into the membership card.
        if item.get("subtype") == "list_item":
            front_key = (item.get("front") or "").strip().casefold()
            if front_key and front_key in seen_front:
                continue
            if front_key:
                seen_front.add(front_key)
            result.append(item)
            continue

        wiki_ids = item.get("wiki_ids_cited") or []
        primary = next(iter(wiki_ids), None)
        if primary and primary in seen_wiki:
            continue

        if item.get("subtype") == "term_definition":
            front_key = (item.get("front") or "").strip().casefold()
            if front_key and front_key in seen_front:
                continue
            if front_key:
                seen_front.add(front_key)

        if primary:
            seen_wiki.add(primary)
        result.append(item)

    return result


def ensure_list_flashcards(
    items: list[dict[str, Any]],
    concepts: list[Any],
) -> list[dict[str, Any]]:
    """Add a membership card and one card per list component the model skipped."""
    covered_wiki = {
        str(wiki_id)
        for item in items
        for wiki_id in (item.get("wiki_ids_cited") or [])
    }
    covered_front = {
        str(item.get("front") or "").strip().casefold()
        for item in items
        if str(item.get("front") or "").strip()
    }
    by_label = {
        concept.preferred_label.strip().casefold(): concept
        for concept in concepts
        if concept.preferred_label.strip()
    }
    extra: list[dict[str, Any]] = []
    for concept in concepts:
        if concept.entry_kind != "list":
            continue
        segments = list(concept.evidence_segment_ids[:1])
        members = _members(concept.items)
        if concept.wiki_id not in covered_wiki:
            overview = concept.definition.strip()
            lines = [overview] if overview else []
            lines.extend(name for name, _details in members)
            extra.append(
                _flashcard(
                    subtype="list",
                    front=concept.preferred_label,
                    back="\n".join(lines),
                    wiki_id=concept.wiki_id,
                    segment_ids=segments,
                    tags=["list"],
                ),
            )
            covered_wiki.add(concept.wiki_id)
            covered_front.add(concept.preferred_label.strip().casefold())
        for name, details in members:
            key = name.casefold()
            if key in covered_front:
                continue
            match = by_label.get(key)
            if match and match.wiki_id not in covered_wiki:
                back = match.definition.strip()
                if match.significance:
                    back = f"{back}\n{match.significance}".strip()
                extra.append(
                    _flashcard(
                        subtype="term_definition",
                        front=match.preferred_label,
                        back=back,
                        wiki_id=match.wiki_id,
                        segment_ids=list(match.evidence_segment_ids[:1]) or segments,
                        tags=["list-component"],
                    ),
                )
                covered_wiki.add(match.wiki_id)
                covered_front.add(key)
                continue
            if match or not details:
                covered_front.add(key)
                continue
            extra.append(
                _flashcard(
                    subtype="list_item",
                    front=name,
                    back=details,
                    wiki_id=concept.wiki_id,
                    segment_ids=segments,
                    tags=["list-component"],
                ),
            )
            covered_front.add(key)
    return [*items, *extra]


def _members(items: list[Any]) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    for raw in items:
        if isinstance(raw, dict):
            name = str(raw.get("name") or "").strip()
            details = str(raw.get("details") or "").strip()
        else:
            name = str(raw).strip()
            details = ""
        if name:
            members.append((name, details))
    return members


def _flashcard(
    *,
    subtype: str,
    front: str,
    back: str,
    wiki_id: str,
    segment_ids: list[str],
    tags: list[str],
) -> dict[str, Any]:
    return {
        "type": "flashcard",
        "subtype": subtype,
        "difficulty": "easy",
        "wiki_ids_cited": [wiki_id],
        "source_chunk_ids": segment_ids,
        "front": front,
        "back": back,
        "tags": tags,
    }


def _dedup_rank(item: dict[str, Any]) -> tuple[int, int, int]:
    is_term_definition = 0 if item.get("subtype") == "term_definition" else 1
    citation_count = len(item.get("source_chunk_ids") or [])
    definition_length = len(item.get("back") or "")
    return (is_term_definition, -citation_count, -definition_length)
