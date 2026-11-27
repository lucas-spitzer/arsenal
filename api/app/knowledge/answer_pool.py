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
TRUE_FALSE_KINDS = frozenset({TRUE_FALSE, "true_false"})
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
        # A closed set (every phase, every step) fits with a distractor, so show
        # all of it. Larger pools still sample at least two correct answers.
        if len(correct) < show:
            chosen = list(correct)
        else:
            max_correct = min(len(correct), max(2, show - 1))
            take = rng.randint(min(2, max_correct), max_correct)
            chosen = rng.sample(correct, take)
        fill = rng.sample(distractors, min(len(distractors), show - len(chosen)))
        options = [*chosen, *fill]
        rng.shuffle(options)
        chosen_set = set(chosen)
        return Draw(options=options, correct_answer="; ".join(opt for opt in options if opt in chosen_set))

    chosen_answer = rng.choice(correct)
    fill = rng.sample(distractors, min(len(distractors), show - 1))
    options = [chosen_answer, *fill]
    rng.shuffle(options)
    return Draw(options=options, correct_answer=chosen_answer)


class ShownAnswerError(ValueError):
    """The submitted rendering cannot be graded."""


def grade_shown_answer(
    quiz: dict[str, Any],
    *,
    question: str,
    options: list[str],
    selected_index: int,
) -> tuple[bool, str]:
    """Grade one shown option. Returns whether it was correct and the right answer text."""
    if selected_index < 0 or selected_index >= len(options):
        raise ShownAnswerError("Pick one of the shown options.")
    selected = options[selected_index]
    kind = str(quiz.get("subtype") or quiz.get("question_type") or "multiple_choice")
    pool = pool_or_none(quiz.get("answer_pool"))

    if pool is not None and kind in TRUE_FALSE_KINDS:
        stem = question.strip()
        correct_stems = {text.strip() for text in pool.correct if text.strip()}
        false_stems = {row.text.strip() for row in pool.distractors if row.text.strip()}
        if stem in correct_stems:
            expected = "True"
        elif stem in false_stems:
            expected = "False"
        else:
            raise ShownAnswerError("That statement is not part of this question.")
        return selected == expected, expected

    if pool is not None and any(text.strip() for text in pool.correct):
        correct = [text.strip() for text in pool.correct if text.strip()]
        correct_set = set(correct)
        picked = selected.strip()
        is_correct = picked in correct_set
        shown = [option.strip() for option in options if option.strip() in correct_set]
        right = picked if is_correct else (shown[0] if shown else correct[0])
        return is_correct, right

    stored = str(quiz.get("correct_answer") or "")
    return _option_matches_stored(stored, selected, selected_index), _stored_option_text(stored, options)


def grade_shown_selection(
    quiz: dict[str, Any],
    *,
    options: list[str],
    selected_indices: list[int],
) -> tuple[bool, list[str]]:
    """Grade a multiple-selection answer against the options that were shown.

    Right means the selected set equals the shown options that are correct.
    One missing answer or one selected distractor fails the question.
    """
    if not options:
        raise ShownAnswerError("That question has no options.")
    if not selected_indices:
        raise ShownAnswerError("Pick at least one option.")
    if len(set(selected_indices)) != len(selected_indices):
        raise ShownAnswerError("Each option can be selected once.")
    if any(index < 0 or index >= len(options) for index in selected_indices):
        raise ShownAnswerError("Pick from the shown options.")

    shown_correct = _shown_correct_options(quiz, options)
    selected = [options[index].strip() for index in selected_indices]
    correct_texts = [option.strip() for option in shown_correct]
    return set(selected) == set(correct_texts), correct_texts


def _shown_correct_options(quiz: dict[str, Any], options: list[str]) -> list[str]:
    pool = pool_or_none(quiz.get("answer_pool"))
    if pool is not None and any(text.strip() for text in pool.correct):
        correct_set = {text.strip() for text in pool.correct if text.strip()}
        return [option for option in options if option.strip() in correct_set]
    stored = {part.strip() for part in str(quiz.get("correct_answer") or "").split(";") if part.strip()}
    return [option for option in options if option.strip() in stored]


def cited_wiki_id(quiz: dict[str, Any]) -> str | None:
    citations = quiz.get("citations")
    if not isinstance(citations, list):
        return None
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        uri = citation.get("uri")
        if isinstance(uri, str) and uri.startswith("wiki://"):
            wiki_id = uri.removeprefix("wiki://").strip()
            return wiki_id or None
    return None


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


def _option_matches_stored(stored: str, option: str, index: int) -> bool:
    answer = stored.strip()
    if not answer:
        return False
    if answer == option:
        return True
    if len(answer) == 1 and answer.isalpha() and ord(answer.upper()) - 65 == index:
        return True
    if answer.isdigit() and int(answer) == index:
        return True
    return False


def _stored_option_text(stored: str, options: list[str]) -> str:
    answer = stored.strip()
    if answer in options:
        return answer
    if len(answer) == 1 and answer.isalpha():
        index = ord(answer.upper()) - 65
        if 0 <= index < len(options):
            return options[index]
    if answer.isdigit():
        index = int(answer)
        if 0 <= index < len(options):
            return options[index]
    return answer


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
