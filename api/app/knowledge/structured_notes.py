"""Read a knowledge upload that is already structured wiki entries.

Accepted shapes:

- ``{"terms": [...], "key_lists": [...], "elos": [...], "compares": [...]}`` (notes export)
- ``{"abbreviations": [...], "questions": [...]}`` (question pack), alone or beside the notes export
- ``{"entries": [ ... ], "unparsed_fragments": [ ... ]}`` (model output or a wiki export)
- a bare array of entries
- one entry object

A term needs a label and a definition. A list needs a label plus an overview
or at least one item. An ELO needs ``elo`` and ``response``. An abbreviation
needs ``abbreviation``, ``title``, and ``definition``. A compare needs ``a``,
``b``, and at least one diff. A question needs a stem, one correct answer, and
one distractor. An optional ``image`` is a file name, or an object with
``filename`` and ``alt``. The file name is a base name, not a path.
``prerequisites`` (wiki export) is accepted as ``prerequisite_labels``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.intellex.wiki_candidates import normalize_items
from app.knowledge.answer_pool import BLOOM_LEVELS, TRUE_FALSE, AnswerPool, AnswerPoolError, Distractor, validate_pool
from app.knowledge.cards import QUESTION_FORMATS

_DOCUMENT_KEYS = ("terms", "key_lists", "elos", "abbreviations", "compares", "questions")
_DIFFICULTIES = ("easy", "medium", "hard")


class StructuredNotesError(ValueError):
    """The text is JSON, but it is not usable wiki entries."""


@dataclass(frozen=True)
class StructuredNotes:
    entries: list[dict[str, Any]]
    unparsed_fragments: list[str]
    questions: list[dict[str, Any]] = field(default_factory=list)


def parse_structured_notes(text: str) -> StructuredNotes | None:
    """Return entries when ``text`` is structured JSON, else ``None``.

    Prose, and text that only looks like it might be JSON, returns ``None``
    so the structuring model can still read it. Valid JSON in the wrong shape
    raises ``StructuredNotesError``.
    """
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return _notes_from_payload(payload)


def require_structured_notes(text: str, *, filename: str) -> StructuredNotes:
    """Parse a ``.json`` upload. Invalid JSON or a missing entry is an error."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StructuredNotesError(f"Could not read '{filename}' as JSON.") from exc
    try:
        return _notes_from_payload(payload)
    except StructuredNotesError as exc:
        raise StructuredNotesError(f"{filename}: {exc}") from exc


def _notes_from_payload(payload: Any) -> StructuredNotes:
    if isinstance(payload, dict) and any(key in payload for key in _DOCUMENT_KEYS):
        return _notes_from_chapter(payload)

    fragments: list[Any]
    if isinstance(payload, list):
        raw_entries = payload
        fragments = []
    elif isinstance(payload, dict) and "entries" in payload:
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise StructuredNotesError("entries must be an array.")
        raw_fragments = payload.get("unparsed_fragments") or []
        fragments = raw_fragments if isinstance(raw_fragments, list) else []
    elif isinstance(payload, dict) and _label(payload) and (_definition(payload) or _items(payload)):
        raw_entries = [payload]
        fragments = []
    else:
        raise StructuredNotesError(
            "JSON needs an entries array, or terms, key_lists, elos, and compares. "
            "A question pack needs abbreviations or questions. "
            "Each term needs a label and a definition. Each ELO needs an elo and a response. "
            "Each compare needs two poles and at least one diff.",
        )

    entries = [normalized for raw in raw_entries if (normalized := _normalize_entry(raw))]
    if not entries:
        raise StructuredNotesError(
            "JSON needs at least one entry with a label and a definition.",
        )
    return StructuredNotes(
        entries=entries,
        unparsed_fragments=[str(fragment) for fragment in fragments if str(fragment).strip()],
    )


def _notes_from_chapter(payload: dict[str, Any]) -> StructuredNotes:
    raw_terms = _array(payload, "terms")
    raw_lists = _array(payload, "key_lists")
    raw_elos = _array(payload, "elos")
    raw_abbreviations = _array(payload, "abbreviations")
    raw_compares = _array(payload, "compares")
    raw_questions = _array(payload, "questions")

    entries: list[dict[str, Any]] = []

    for raw in raw_terms:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("term") or raw.get("label") or raw.get("preferred_label") or "").strip()
        definition = str(raw.get("definition") or "").strip()
        if not label or not definition:
            continue
        entries.append(
            _entry(
                label=label,
                definition=definition,
                entry_kind="term",
                significance=_optional_text(raw.get("significance")),
                category=_optional_text(raw.get("category")),
                importance=str(raw.get("importance") or "supporting"),
                elo_reference=_optional_text(raw.get("elo_reference")),
            ),
        )

    for raw in raw_lists:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("concept") or raw.get("label") or raw.get("preferred_label") or "").strip()
        if not label:
            continue
        items = _items(raw)
        category = _optional_text(raw.get("category"))
        overview = str(raw.get("overview") or raw.get("definition") or "").strip()
        if not overview and not items:
            continue
        entries.append(
            _entry(
                label=label,
                definition=overview,
                entry_kind="list",
                category=category,
                items=items,
                importance=str(raw.get("importance") or "supporting"),
                elo_reference=_optional_text(raw.get("elo_reference")),
            ),
        )

    elo_index = 0
    for raw in raw_elos:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("elo") or raw.get("label") or raw.get("preferred_label") or "").strip()
        definition = str(raw.get("response") or raw.get("definition") or "").strip()
        if not label or not definition:
            continue
        entries.append(
            _entry(
                label=label,
                definition=definition,
                entry_kind="elo",
                elo_index=elo_index,
            ),
        )
        elo_index += 1

    entries.extend(_abbreviations(raw_abbreviations))
    entries.extend(_compares(raw_compares))
    questions = _questions(raw_questions, entries)

    if not entries and not questions:
        raise StructuredNotesError(
            "JSON needs at least one term with a definition, one list with items, "
            "one ELO with a response, one abbreviation, one compare, or one question.",
        )
    return StructuredNotes(entries=entries, unparsed_fragments=[], questions=questions)


def _normalize_entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = _kind(raw)
    if kind == "compare":
        left = str(raw.get("a") or "").strip()
        right = str(raw.get("b") or "").strip()
        diffs = _compare_diffs(raw)
        label = _label(raw) or (f"{left} vs {right}" if left and right else "")
        if not label or not diffs:
            return None
        aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
        pole_aliases = [pole for pole in (left, right) if pole]
        return _entry(
            label=label,
            definition=_definition(raw),
            entry_kind="compare",
            significance=_optional_text(raw.get("significance")),
            category=_optional_text(raw.get("category")),
            items=diffs,
            aliases=[str(alias) for alias in aliases if str(alias).strip()] or pole_aliases,
            importance=str(raw.get("importance") or "supporting"),
            note_excerpt=str(raw.get("note_excerpt") or ""),
        )
    label = _label(raw)
    if not label:
        return None
    definition = _definition(raw)
    items = _items(raw)
    if kind == "list":
        if not definition and not items:
            return None
    elif not definition:
        return None
    prerequisites = raw.get("prerequisite_labels")
    if not isinstance(prerequisites, list):
        prerequisites = raw.get("prerequisites") if isinstance(raw.get("prerequisites"), list) else []
    aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
    pronunciation = raw.get("pronunciation")
    raw_index = raw.get("elo_index")
    elo_index = raw_index if isinstance(raw_index, int) and not isinstance(raw_index, bool) else None
    return _entry(
        label=label,
        definition=definition,
        entry_kind=kind,
        significance=_optional_text(raw.get("significance")),
        category=_optional_text(raw.get("category")),
        items=items,
        aliases=[str(alias) for alias in aliases if str(alias).strip()],
        pronunciation=str(pronunciation) if pronunciation else None,
        importance=str(raw.get("importance") or "supporting"),
        prerequisite_labels=[str(item) for item in prerequisites if str(item).strip()],
        note_excerpt=str(raw.get("note_excerpt") or ""),
        elo_reference=_optional_text(raw.get("elo_reference")),
        elo_index=elo_index,
    )


def _entry(
    *,
    label: str,
    definition: str,
    entry_kind: str,
    significance: str | None = None,
    category: str | None = None,
    items: list[dict[str, str]] | None = None,
    aliases: list[str] | None = None,
    pronunciation: str | None = None,
    importance: str = "supporting",
    prerequisite_labels: list[str] | None = None,
    note_excerpt: str = "",
    elo_reference: str | None = None,
    elo_index: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "definition": definition,
        "entry_kind": _entry_kind(entry_kind),
        "significance": significance,
        "category": category,
        "items": items or [],
        "aliases": aliases or [],
        "pronunciation": pronunciation,
        "importance": importance or "supporting",
        "prerequisite_labels": prerequisite_labels or [],
        "note_excerpt": note_excerpt,
    }
    if elo_reference:
        row["elo_reference"] = elo_reference
    if elo_index is not None:
        row["elo_index"] = elo_index
    return row


def _label(raw: dict[str, Any]) -> str:
    return str(raw.get("label") or raw.get("preferred_label") or "").strip()


def _definition(raw: dict[str, Any]) -> str:
    return str(raw.get("definition") or raw.get("overview") or "").strip()


def _entry_kind(entry_kind: str) -> str:
    kind = entry_kind.strip().lower()
    if kind in {"list", "elo", "abbreviation", "compare"}:
        return kind
    return "term"


def _array(payload: dict[str, Any], key: str) -> list[Any]:
    raw = payload.get(key) or []
    if not isinstance(raw, list):
        raise StructuredNotesError(f"{key} must be an array.")
    return raw


def _abbreviations(raw_items: list[Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise StructuredNotesError(f"Abbreviation {index} must be an object.")
        label = str(raw.get("abbreviation") or "").strip()
        title = str(raw.get("title") or "").strip()
        definition = str(raw.get("definition") or "").strip()
        if not label or not title or not definition:
            raise StructuredNotesError(f"Abbreviation {index} needs an abbreviation, a title, and a definition.")
        key = label.casefold()
        if key in seen:
            raise StructuredNotesError(f"Abbreviation '{label}' is repeated.")
        seen.add(key)
        entries.append(
            _entry(
                label=label,
                definition=definition,
                entry_kind="abbreviation",
                significance=title,
                category=_optional_text(raw.get("category")),
                aliases=[title],
            ),
        )
    return entries


def _questions(raw_items: list[Any], _entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise StructuredNotesError(f"Question {index} must be an object.")
        stem = " ".join(str(raw.get("question") or "").split())
        if not stem:
            raise StructuredNotesError(f"Question {index} needs a question.")
        fmt = str(raw.get("format") or "multiple_choice").strip().lower()
        if fmt not in QUESTION_FORMATS:
            raise StructuredNotesError(f"Question {index} uses an unknown format.")
        correct = _correct_answers(raw.get("correct"))
        distractors = _question_distractors(raw.get("distractors"))
        if not correct:
            raise StructuredNotesError(f"Question {index} needs a correct answer.")
        if not distractors:
            raise StructuredNotesError(f"Question {index} needs a distractor.")
        difficulty = str(raw.get("difficulty") or "medium").strip().lower()
        if difficulty not in _DIFFICULTIES:
            raise StructuredNotesError(f"Question {index} uses an unknown difficulty.")
        bloom = _optional_text(raw.get("bloom_level"))
        if bloom and bloom not in BLOOM_LEVELS:
            raise StructuredNotesError(f"Question {index} uses an unknown cognitive level.")
        citation = _question_citation(raw, index)
        pool = AnswerPool(
            correct=correct,
            distractors=distractors,
            show_count=2 if fmt == TRUE_FALSE else 4,
        )
        try:
            validate_pool(pool, fmt)
        except AnswerPoolError as exc:
            raise StructuredNotesError(f"Question {index}: {exc}") from exc
        questions.append(
            {
                "question": stem,
                "format": fmt,
                "citation": citation,
                "pool": pool.model_dump(),
                "explanation": _optional_text(raw.get("explanation")),
                "difficulty": difficulty,
                "bloom_level": bloom,
                "image": _question_image(raw, index),
            },
        )
    return questions


_CITE_FIELDS = (
    ("abbreviation", "abbreviation"),
    ("term", "term"),
    ("concept", "list"),
    ("compare", "compare"),
)


def _question_image(raw: dict[str, Any], index: int) -> dict[str, str] | None:
    """A supporting image named in the question pack, or none."""
    if "image" not in raw or raw.get("image") is None:
        return None
    value = raw.get("image")
    if isinstance(value, str):
        filename = value.strip()
        if not filename:
            return None
        alt = ""
    elif isinstance(value, dict):
        filename = str(value.get("filename") or "").strip()
        if not filename:
            raise StructuredNotesError(f"Question {index} image needs a filename.")
        alt = " ".join(str(value.get("alt") or "").split())
    else:
        raise StructuredNotesError(f"Question {index} image must be a filename.")
    if filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise StructuredNotesError(f"Question {index} image filename must be a file name, not a path.")
    return {"filename": filename, "alt": alt}


def _question_citation(raw: dict[str, Any], index: int) -> dict[str, str] | None:
    found: list[dict[str, str]] = []
    for field, kind in _CITE_FIELDS:
        label = _optional_text(raw.get(field))
        if label:
            found.append({"kind": kind, "label": label})
    if len(found) > 1:
        raise StructuredNotesError(f"Question {index} cites more than one entry.")
    return found[0] if found else None


def _correct_answers(value: Any) -> list[str]:
    if isinstance(value, str):
        text = " ".join(value.split())
        return [text] if text else []
    if not isinstance(value, list):
        return []
    answers: list[str] = []
    for item in value:
        text = " ".join(str(item).split())
        if text:
            answers.append(text)
    return answers


def _question_distractors(value: Any) -> list[Distractor]:
    if not isinstance(value, list):
        return []
    rows: list[Distractor] = []
    for item in value:
        if isinstance(item, str):
            text = " ".join(item.split())
            misconception = ""
        elif isinstance(item, dict):
            text = " ".join(str(item.get("text") or "").split())
            misconception = " ".join(str(item.get("misconception") or "").split())
        else:
            continue
        if text:
            rows.append(Distractor(text=text, misconception=misconception))
    return rows


def _kind(raw: dict[str, Any]) -> str:
    return _entry_kind(str(raw.get("entry_kind") or "term"))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _items(raw: dict[str, Any]) -> list[dict[str, str]]:
    return normalize_items(raw.get("items"))


def _compare_diffs(raw: dict[str, Any]) -> list[dict[str, str]]:
    """Accept chapter ``diffs`` or already-normalized ``items`` with ``a``/``b``."""
    if isinstance(raw.get("diffs"), list):
        return normalize_items(raw.get("diffs"))
    return [item for item in normalize_items(raw.get("items")) if item.get("a") and item.get("b")]


def _compares(raw_items: list[Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise StructuredNotesError(f"Compare {index} must be an object.")
        left = str(raw.get("a") or "").strip()
        right = str(raw.get("b") or "").strip()
        if not left or not right:
            raise StructuredNotesError(f"Compare {index} needs poles a and b.")
        diffs = _compare_diffs(raw)
        if not diffs:
            raise StructuredNotesError(f"Compare {index} needs at least one diff.")
        for diff_index, diff in enumerate(diffs, start=1):
            if not diff.get("a") or not diff.get("b"):
                raise StructuredNotesError(
                    f"Compare {index} diff {diff_index} needs a dimension, a, and b.",
                )
        entries.append(
            _entry(
                label=f"{left} vs {right}",
                definition=str(raw.get("overview") or raw.get("definition") or "").strip(),
                entry_kind="compare",
                significance=_optional_text(raw.get("significance")),
                category=_optional_text(raw.get("category")),
                items=diffs,
                aliases=[left, right],
                importance=str(raw.get("importance") or "supporting"),
                elo_reference=_optional_text(raw.get("elo_reference")),
            ),
        )
    return entries
