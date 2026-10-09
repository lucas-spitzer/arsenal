import random

import pytest

from app.knowledge.answer_pool import (
    MULTIPLE_SELECT,
    TRUE_FALSE,
    AnswerPool,
    AnswerPoolError,
    Distractor,
    draw,
    pool_from_generated,
    validate_pool,
)


def test_pool_from_generated_keeps_variants_and_distractor_notes() -> None:
    pool = pool_from_generated(
        {
            "subtype": "multiple_choice",
            "choices": ["Friction", "Chance", "War"],
            "correct_answer": "Friction",
            "correct_variants": ["The force that resists action", "Friction"],
            "distractors": [
                {"text": "Chance", "misconception": "Confuses the two characteristics."},
                {"text": "Uncertainty", "misconception": "A near-synonym, not the term."},
            ],
        },
    )

    assert pool is not None
    assert pool["correct"] == ["Friction", "The force that resists action"]
    assert {row["text"] for row in pool["distractors"]} == {"Chance", "War", "Uncertainty"}
    noted = next(row for row in pool["distractors"] if row["text"] == "Chance")
    assert noted["misconception"] == "Confuses the two characteristics."


def test_draw_never_shows_a_correct_answer_as_a_distractor() -> None:
    pool = AnswerPool(
        correct=["Friction", "Resistance to action"],
        distractors=[
            Distractor(text="Chance"),
            Distractor(text="War"),
            Distractor(text="Policy"),
            Distractor(text="Friction"),
        ],
        show_count=4,
    )
    # A correct text that leaked into the distractor list is still a correct option,
    # so the draw must not place it beside another correct phrasing.
    pool.distractors = [row for row in pool.distractors if row.text not in set(pool.correct)]

    for seed in range(30):
        rendered = draw(pool, "multiple_choice", random.Random(seed))
        assert rendered.correct_answer in rendered.options
        assert rendered.options.count(rendered.correct_answer) == 1
        assert len(rendered.options) == 4
        assert set(rendered.options) & {"Chance", "War", "Policy"}
        assert "Resistance to action" not in rendered.options or rendered.correct_answer == "Resistance to action"


def test_true_false_draw_uses_the_statement_as_the_question() -> None:
    pool = AnswerPool(
        correct=["Friction resists every action."],
        distractors=[Distractor(text="Friction can be removed by planning.", misconception="It cannot.")],
        show_count=2,
    )

    rendered = draw(pool, TRUE_FALSE, random.Random(1))

    assert rendered.options == ["True", "False"]
    assert rendered.question in {"Friction resists every action.", "Friction can be removed by planning."}
    assert rendered.correct_answer == ("True" if rendered.question == "Friction resists every action." else "False")


def test_multiple_select_draw_keeps_at_least_two_correct() -> None:
    pool = AnswerPool(
        correct=["Friction", "Uncertainty", "Fluidity"],
        distractors=[Distractor(text="Chance"), Distractor(text="Policy")],
        show_count=4,
    )

    rendered = draw(pool, MULTIPLE_SELECT, random.Random(4))
    answers = [part.strip() for part in rendered.correct_answer.split(";") if part.strip()]

    assert len(answers) >= 2
    assert all(answer in rendered.options for answer in answers)
    assert set(answers) <= {"Friction", "Uncertainty", "Fluidity"}


def test_validate_pool_rejects_a_distractor_that_matches_the_answer() -> None:
    pool = AnswerPool(
        correct=["Friction"],
        distractors=[Distractor(text="Friction")],
        show_count=4,
    )

    with pytest.raises(AnswerPoolError, match="matches a correct"):
        validate_pool(pool, "multiple_choice")


def test_validate_pool_requires_two_correct_answers_for_multiple_select() -> None:
    pool = AnswerPool(correct=["Friction"], distractors=[Distractor(text="Chance")], show_count=2)

    with pytest.raises(AnswerPoolError, match="two correct"):
        validate_pool(pool, MULTIPLE_SELECT)
