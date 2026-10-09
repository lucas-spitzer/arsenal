from __future__ import annotations

import uuid
from typing import Any, Literal

from app.knowledge.answer_pool import BLOOM_LEVELS, pool_from_generated

ArtifactType = Literal["flashcard", "quiz", "scenario"]

_VALID_DIFFICULTIES = {"easy", "medium", "hard"}


def normalize_difficulty(value: Any) -> str:
    """Coerce a model-emitted difficulty onto the DB-allowed enum.

    The ``{flashcards,quizzes,scenarios}_difficulty_check`` constraints only
    permit ``easy|medium|hard``. Models routinely improvise values like
    ``"medium-hard"``, ``"very easy"``, or ``"challenging"``; map those onto a
    valid bucket rather than letting the insert fail.
    """
    if not isinstance(value, str):
        return "medium"

    cleaned = value.strip().lower()
    if cleaned in _VALID_DIFFICULTIES:
        return cleaned
    if "hard" in cleaned:
        return "hard"
    if "easy" in cleaned:
        return "easy"
    return "medium"


def normalize_question_type(subtype: str | None) -> str:
    mapping = {
        "multiple_choice": "multiple_choice",
        "true_false": "true_false",
        "true_false_correction": "true_false",
        "short_answer": "short_answer",
        "multiple_select": "multiple_choice",
    }
    return mapping.get(subtype or "multiple_choice", "multiple_choice")


def assessment_item_to_flashcard(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "front": item.get("front") or "",
        "back": item.get("back") or "",
        "difficulty": normalize_difficulty(item.get("difficulty")),
        "tags": item.get("tags") or [],
        "wiki_ids_cited": item.get("wiki_ids_cited") or [],
        "segment_ids_used": item.get("source_chunk_ids") or [],
    }


def normalize_bloom_level(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned if cleaned in BLOOM_LEVELS else None


def assessment_item_to_quiz(item: dict[str, Any]) -> dict[str, Any]:
    subtype = item.get("subtype") or "multiple_choice"
    correct_answer = item.get("correct_answer") or ""
    choices = item.get("choices") or []

    if subtype == "multiple_select" and isinstance(correct_answer, list):
        correct_answer = "; ".join(correct_answer)

    return {
        "question": item.get("question") or "",
        "question_type": normalize_question_type(subtype),
        "options": choices,
        "correct_answer": correct_answer,
        "answer_pool": pool_from_generated(item) or {},
        "bloom_level": normalize_bloom_level(item.get("bloom_level")),
        "explanation": item.get("explanation"),
        "difficulty": normalize_difficulty(item.get("difficulty")),
        "wiki_ids_cited": item.get("wiki_ids_cited") or [],
        "segment_ids_used": item.get("source_chunk_ids") or [],
    }


def assessment_item_to_scenario(item: dict[str, Any]) -> dict[str, Any]:
    task = item.get("task") or item.get("prompt") or ""
    situation = item.get("situation") or item.get("context")
    rubric = item.get("rubric") or {}
    criteria = item.get("expected_response_elements") or []

    if isinstance(rubric, dict) and not criteria:
        criteria = [str(value) for value in rubric.values() if value]

    return {
        "title": item.get("title") or task[:80] or "Scenario",
        "prompt": task,
        "context": situation,
        "evaluation_criteria": criteria,
        "bloom_level": normalize_bloom_level(item.get("bloom_level")),
        "difficulty": normalize_difficulty(item.get("difficulty")),
        "wiki_ids_cited": item.get("wiki_ids_cited") or [],
        "segment_ids_used": item.get("source_chunk_ids") or [],
    }


def ensure_item_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for item in items:
        row = dict(item)
        if not row.get("item_id"):
            row["item_id"] = str(uuid.uuid4())
        normalized.append(row)

    return normalized
