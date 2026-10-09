"""Randomizable answers for a quiz question.

A pool keeps more answers than one rendering shows: several phrasings of the
correct answer and a larger set of distractors, each with the misconception it
represents. The Academy draws from the pool at study time so a learner cannot
memorize option order or wording. ``options`` and ``correct_answer`` on the row
hold one draw so older readers keep working.
"""

from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel, Field

BLOOM_LEVELS = ("remember", "understand", "apply", "analyze")
TRUE_FALSE = "true_false_correction"
MULTIPLE_SELECT = "multiple_select"
TRUE_FALSE_OPTIONS = ["True", "False"]


class AnswerPoolError(ValueError):
    """The pool cannot produce a valid question."""


class Distractor(BaseModel):
    text: str
    misconception: str = ""
    confused_with_wiki_id: str | None = None


class AnswerPool(BaseModel):
    correct: list[str] = Field(default_factory=list)
    distractors: list[Distractor] = Field(default_factory=list)
    show_count: int = 4


class Draw(BaseModel):
    """One rendering of a question from its pool."""

    question: str | None = None
    options: list[str]
    correct_answer: str


def pool_from_generated(item: dict[str, Any]) -> dict[str, Any] | None:
    """Build a pool from a model-emitted quiz item, or ``None`` when it has no choices."""
    subtype = str(item.get("subtype") or "multiple_choice")
    choices = [_clean(choice) for choice in item.get("choices") or []]
    choices = [choice for choice in choices if choice]
    answer = item.get("correct_answer")
    variants = [_clean(text) for text in item.get("correct_variants") or []]
    given = [_distractor(raw) for raw in item.get("distractors") or []]
    given = [row for row in given if row.text]

    if subtype == TRUE_FALSE:
        statement = _clean(item.get("question"))
        is_true = str(answer or "").strip().lower() == "true"
        correct = _dedupe([*([statement] if is_true else []), *variants])
        distractors = list(given)
        if not is_true and statement and all(row.text != statement for row in distractors):
            distractors.insert(0, Distractor(text=statement, misconception=_clean(item.get("explanation"))))
        if not correct and not distractors:
            return None
        return AnswerPool(correct=correct, distractors=_dedupe_distractors(distractors, set(correct)), show_count=2).model_dump()

    if not choices:
        return None

    if subtype == MULTIPLE_SELECT:
        if isinstance(answer, list):
            answers = [_clean(part) for part in answer]
        else:
            answers = [part.strip() for part in str(answer or "").split(";") if part.strip()]
        correct = _dedupe([*answers, *variants])
    else:
        correct = _dedupe([_clean(answer), *variants])
    correct_set = set(correct)
    distractors = [Distractor(text=choice) for choice in choices if choice not in correct_set]
    for row in given:
        if row.text in correct_set:
            continue
        existing = next((item for item in distractors if item.text == row.text), None)
        if existing is None:
            distractors.append(row)
        elif row.misconception and not existing.misconception:
            existing.misconception = row.misconception
            existing.confused_with_wiki_id = existing.confused_with_wiki_id or row.confused_with_wiki_id
    if not correct:
        return None
    return AnswerPool(
        correct=correct,
        distractors=_dedupe_distractors(distractors, correct_set),
        show_count=max(2, len(choices)) if choices else 4,
    ).model_dump()


def validate_pool(pool: AnswerPool, subtype: str) -> None:
    """Raise ``AnswerPoolError`` when the pool cannot render a question."""
    correct = [text for text in pool.correct if text.strip()]
    distractors = [row for row in pool.distractors if row.text.strip()]
    if len(set(correct)) != len(correct):
        raise AnswerPoolError("Correct answers repeat.")
    texts = [row.text for row in distractors]
    if len(set(texts)) != len(texts):
        raise AnswerPoolError("Distractors repeat.")
    if set(texts) & set(correct):
        raise AnswerPoolError("A distractor matches a correct answer.")
    if subtype == TRUE_FALSE:
        if not correct and not distractors:
            raise AnswerPoolError("Add at least one true or false statement.")
        return
    if not correct:
        raise AnswerPoolError("Add at least one correct answer.")
    if subtype == MULTIPLE_SELECT and len(correct) < 2:
        raise AnswerPoolError("Multiple select needs at least two correct answers.")
    if not distractors:
        raise AnswerPoolError("Add at least one distractor.")
    if pool.show_count < 2:
        raise AnswerPoolError("Show at least two options.")


def draw(pool: AnswerPool, subtype: str, rng: random.Random | None = None) -> Draw:
    """Pick one rendering: shuffled options and the matching correct answer."""
    rng = rng or random.Random()
    correct = [text for text in pool.correct if text.strip()]
    distractors = [row.text for row in pool.distractors if row.text.strip()]

    if subtype == TRUE_FALSE:
        statements = [(text, True) for text in correct] + [(text, False) for text in distractors]
        if not statements:
            raise AnswerPoolError("No statements to draw.")
        statement, is_true = rng.choice(statements)
        return Draw(question=statement, options=list(TRUE_FALSE_OPTIONS), correct_answer="True" if is_true else "False")

    if not correct:
        raise AnswerPoolError("No correct answer to draw.")
    show = max(2, pool.show_count)
    if subtype == MULTIPLE_SELECT:
        max_correct = min(len(correct), max(2, show - 1))
        take = rng.randint(min(2, max_correct), max_correct)
        chosen = rng.sample(correct, take)
        fill = rng.sample(distractors, min(len(distractors), show - take))
        options = [*chosen, *fill]
        rng.shuffle(options)
        return Draw(options=options, correct_answer="; ".join(opt for opt in options if opt in set(chosen)))

    chosen_answer = rng.choice(correct)
    fill = rng.sample(distractors, min(len(distractors), show - 1))
    options = [chosen_answer, *fill]
    rng.shuffle(options)
    return Draw(options=options, correct_answer=chosen_answer)


def pool_or_none(raw: Any) -> AnswerPool | None:
    if not isinstance(raw, dict) or not raw:
        return None
    pool = AnswerPool.model_validate(raw)
    if not pool.correct and not pool.distractors:
        return None
    return pool


def _distractor(raw: Any) -> Distractor:
    if isinstance(raw, dict):
        return Distractor(
            text=_clean(raw.get("text")),
            misconception=_clean(raw.get("misconception")),
            confused_with_wiki_id=(str(raw["confused_with_wiki_id"]) if raw.get("confused_with_wiki_id") else None),
        )
    return Distractor(text=_clean(raw))


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _dedupe_distractors(rows: list[Distractor], correct: set[str]) -> list[Distractor]:
    seen: set[str] = set()
    out: list[Distractor] = []
    for row in rows:
        if not row.text or row.text in correct or row.text in seen:
            continue
        seen.add(row.text)
        out.append(row)
    return out
