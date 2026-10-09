from __future__ import annotations

import re
from typing import Any

from app.qngen.canonical_context import ConceptCard

_MAX_FLASHCARDS_PER_CONCEPT = 2
_MAX_QUIZZES_PER_CONCEPT = 1
_MAX_SCENARIOS_PER_CONCEPT = 1

# Leading option label on a model-emitted answer, e.g. "B) ", "(B) ", "B. ", "B- ".
_LABEL_PREFIX = re.compile(r"^\s*\(?([A-Za-z])\)?[.):\-]\s+")


def validate_assessment_items(
    *,
    items: list[dict[str, Any]],
    concepts: list[ConceptCard],
    segment_ids: set[str],
    wiki_ids: set[str],
    max_per_concept: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Drop ungrounded or unanswerable items and cap items per concept.

    ``max_per_concept`` overrides the quiz and scenario caps when a caller
    asks for several variants of one concept.
    """
    quiz_cap = max_per_concept or _MAX_QUIZZES_PER_CONCEPT
    scenario_cap = max_per_concept or _MAX_SCENARIOS_PER_CONCEPT
    labels_by_wiki_id = {
        concept.wiki_id: {
            concept.preferred_label.lower(),
            *[alias.lower() for alias in concept.aliases],
        }
        for concept in concepts
    }
    all_labels = {
        label
        for labels in labels_by_wiki_id.values()
        for label in labels
    }

    validated: list[dict[str, Any]] = []
    dropped_invalid_citations = 0
    dropped_invalid_quiz_answer = 0
    repaired_quiz_answer = 0
    dropped_per_concept_cap = 0
    repaired_pool_overlap = 0
    label_warnings: list[str] = []

    flashcard_counts: dict[str, int] = {}
    quiz_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}

    for item in items:
        cited_wiki = set(item.get("wiki_ids_cited") or [])
        cited_segments = set(item.get("source_chunk_ids") or [])

        if cited_wiki - wiki_ids or cited_segments - segment_ids:
            dropped_invalid_citations += 1
            continue

        item_type = item.get("type")
        primary_wiki = next(iter(cited_wiki), None)

        if item_type == "quiz":
            choices = item.get("choices") or []
            correct_answer = item.get("correct_answer")
            subtype = item.get("subtype", "multiple_choice")

            if subtype == "multiple_select":
                if isinstance(correct_answer, str):
                    answers = [part.strip() for part in correct_answer.split(";") if part.strip()]
                    if answers and not all(answer in choices for answer in answers):
                        dropped_invalid_quiz_answer += 1
                        continue
            elif choices and correct_answer not in choices:
                # Single-answer quiz whose answer does not match a choice verbatim.
                # This applies to every choice-bearing subtype (including plain
                # ``true_false``, which previously bypassed the check entirely).
                # Attempt a deterministic repair before dropping.
                coerced = _coerce_answer_to_choice(correct_answer, choices)
                if coerced is None:
                    dropped_invalid_quiz_answer += 1
                    continue
                item = dict(item)
                item["correct_answer"] = coerced
                repaired_quiz_answer += 1

            cleaned, overlapped = _strip_pool_overlap(item)
            if overlapped:
                item = cleaned
                repaired_pool_overlap += 1

        if primary_wiki and item.get("subtype") != "list_item":
            if item_type == "flashcard":
                count = flashcard_counts.get(primary_wiki, 0)
                if count >= _MAX_FLASHCARDS_PER_CONCEPT:
                    dropped_per_concept_cap += 1
                    continue
                flashcard_counts[primary_wiki] = count + 1
            elif item_type == "quiz":
                count = quiz_counts.get(primary_wiki, 0)
                if count >= quiz_cap:
                    dropped_per_concept_cap += 1
                    continue
                quiz_counts[primary_wiki] = count + 1
            elif item_type == "scenario":
                count = scenario_counts.get(primary_wiki, 0)
                if count >= scenario_cap:
                    dropped_per_concept_cap += 1
                    continue
                scenario_counts[primary_wiki] = count + 1

        text_blob = _item_text(item).lower()
        if text_blob and all_labels and not contains_canonical_label(text_blob, all_labels):
            label_warnings.append(
                f"Item {item.get('item_id')} may not reference a canonical label.",
            )

        validated.append(item)

    report = {
        "input_count": len(items),
        "validated_count": len(validated),
        "dropped_invalid_citations": dropped_invalid_citations,
        "dropped_invalid_quiz_answer": dropped_invalid_quiz_answer,
        "repaired_quiz_answer": repaired_quiz_answer,
        "repaired_pool_overlap": repaired_pool_overlap,
        "dropped_per_concept_cap": dropped_per_concept_cap,
        "label_warnings": label_warnings,
    }
    return validated, report


def _strip_pool_overlap(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove model-emitted distractors that repeat a correct answer."""
    distractors = item.get("distractors")
    if not isinstance(distractors, list) or not distractors:
        return item, False
    correct: set[str] = set()
    answer = item.get("correct_answer")
    if isinstance(answer, str):
        correct.update(part.strip().lower() for part in answer.split(";") if part.strip())
    elif isinstance(answer, list):
        correct.update(str(part).strip().lower() for part in answer)
    correct.update(str(text).strip().lower() for text in item.get("correct_variants") or [])

    kept = []
    for raw in distractors:
        text = raw.get("text") if isinstance(raw, dict) else raw
        if str(text or "").strip().lower() in correct:
            continue
        kept.append(raw)
    if len(kept) == len(distractors):
        return item, False
    cleaned = dict(item)
    cleaned["distractors"] = kept
    return cleaned, True


def _item_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("front"),
        item.get("back"),
        item.get("question"),
        item.get("situation"),
        item.get("task"),
    ]
    return " ".join(part for part in parts if isinstance(part, str))


def contains_canonical_label(text: str, labels: set[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(label)}\b", lowered) for label in labels)


def _coerce_answer_to_choice(answer: Any, choices: list[Any]) -> str | None:
    """Best-effort map a model-emitted answer onto one of ``choices`` verbatim.

    Returns the matching choice string, or ``None`` when no confident match
    exists. Covers the failure modes that silently dropped most quiz items:
    case mismatches, option labels ("B) ..."), bare letters ("B"), and answers
    that lead with the choice text ("False - because ...").
    """
    if not isinstance(answer, str) or not choices:
        return None

    answer = answer.strip()
    lower_map = {str(choice).lower(): str(choice) for choice in choices}

    # Case-insensitive exact match.
    if answer.lower() in lower_map:
        return lower_map[answer.lower()]

    # Strip a leading option label such as "B) ", "(B) ", or "B. ".
    label = _LABEL_PREFIX.match(answer)
    if label:
        stripped = answer[label.end():].strip()
        if stripped.lower() in lower_map:
            return lower_map[stripped.lower()]
        indexed = _choice_for_letter(label.group(1), choices)
        if indexed is not None:
            return indexed

    # Bare letter label, e.g. answer == "B".
    if len(answer) == 1:
        indexed = _choice_for_letter(answer, choices)
        if indexed is not None:
            return indexed

    # Answer leads with the choice text followed by a boundary ("False - chance
    # is ..."): prefer the longest such choice so "Warfare ..." beats "War". The
    # boundary check avoids mis-coercing "Falsehood ..." onto "False".
    prefixes = [str(choice) for choice in choices if _leads_with_choice(answer, str(choice))]
    if prefixes:
        return max(prefixes, key=len)

    return None


def _leads_with_choice(answer: str, choice: str) -> bool:
    if not choice or not answer.lower().startswith(choice.lower()):
        return False
    remainder = answer[len(choice):]
    return remainder == "" or not remainder[0].isalnum()


def _choice_for_letter(letter: str, choices: list[Any]) -> str | None:
    if not letter.isalpha():
        return None
    index = ord(letter.upper()) - ord("A")
    if 0 <= index < len(choices):
        return str(choices[index])
    return None
