from app.services.atlas_exams import (
    ExamAssemblyError,
    assemble_full_practice,
    assemble_subject_exam,
    eligible_quizzes,
)
from app.services.atlas_scoring import (
    points_for_correct_answer,
    sort_leaderboard_rows,
    sum_points,
)


def test_first_correct_is_five_points() -> None:
    assert points_for_correct_answer(0) == [("first_correct", 5)]


def test_repeat_correct_is_one_point() -> None:
    assert points_for_correct_answer(1) == [("repeat_correct", 1)]
    assert points_for_correct_answer(2) == [("repeat_correct", 1)]


def test_fifth_correct_includes_mastery_bonus() -> None:
    events = points_for_correct_answer(4)
    assert events == [("repeat_correct", 1), ("mastery_bonus", 3)]
    assert sum_points(events) == 4


def test_path_to_mastery_totals_twelve() -> None:
    total = 0
    for prior in range(5):
        total += sum_points(points_for_correct_answer(prior))
    assert total == 12


def test_leaderboard_tie_break_order() -> None:
    rows = sort_leaderboard_rows(
        [
            {"name": "2ndLt B", "lifetime_ap": 10, "concepts_mastered": 1, "accuracy": 90},
            {"name": "2ndLt A", "lifetime_ap": 10, "concepts_mastered": 2, "accuracy": 80},
            {"name": "2ndLt C", "lifetime_ap": 12, "concepts_mastered": 0, "accuracy": 50},
        ]
    )
    assert [row["name"] for row in rows] == ["2ndLt C", "2ndLt A", "2ndLt B"]


def _quiz(quiz_id: str, *, source_id: str | None = None, lesson_id: str | None = None) -> dict:
    return {
        "id": quiz_id,
        "source_id": source_id,
        "lesson_id": lesson_id,
        "question": f"Question {quiz_id}?",
        "question_type": "multiple_choice",
        "subtype": "multiple_choice",
        "options": ["A", "B", "C", "D"],
        "correct_answer": "A",
        "answer_pool": {
            "correct": ["A"],
            "distractors": [
                {"text": "B", "misconception": ""},
                {"text": "C", "misconception": ""},
                {"text": "D", "misconception": ""},
            ],
            "show_count": 4,
        },
    }


def test_subject_exam_requires_ten_questions() -> None:
    quizzes = [_quiz(f"q-{index}", source_id="src-1") for index in range(9)]
    try:
        assemble_subject_exam(quizzes, subject_kind="source", subject_id="src-1", subject_name="Demo")
        raise AssertionError("expected shortage")
    except ExamAssemblyError as exc:
        assert "10" in exc.detail


def test_subject_exam_draws_ten() -> None:
    quizzes = [_quiz(f"q-{index}", source_id="src-1") for index in range(12)]
    shown, snapshot = assemble_subject_exam(
        quizzes,
        subject_kind="source",
        subject_id="src-1",
        subject_name="Demo",
    )
    assert len(shown) == 10
    assert snapshot["question_count"] == 10
    assert len({row["quiz_id"] for row in shown}) == 10


def test_full_practice_quotas_and_exclusions() -> None:
    sources = [
        {"id": "src-wf", "filename": "MCDP 1 Warfighting.pdf", "source_metadata": {}},
        {"id": "src-afo", "filename": "Armed Forces Officer.pdf", "source_metadata": {}},
        {"id": "src-other-a", "filename": "Ops.pdf", "source_metadata": {"display_name": "Operations"}},
        {"id": "src-other-b", "filename": "Comms.pdf", "source_metadata": {"display_name": "Communications"}},
    ]
    lessons = [
        {"id": "les-nav", "title": "Land Navigation"},
        {"id": "les-other", "title": "Uniforms"},
    ]
    quizzes = [
        *[_quiz(f"wf-{i}", source_id="src-wf") for i in range(12)],
        *[_quiz(f"nav-{i}", lesson_id="les-nav") for i in range(12)],
        *[_quiz(f"afo-{i}", source_id="src-afo") for i in range(12)],
        *[_quiz(f"ops-{i}", source_id="src-other-a") for i in range(8)],
        *[_quiz(f"com-{i}", source_id="src-other-b") for i in range(8)],
        *[_quiz(f"uni-{i}", lesson_id="les-other") for i in range(8)],
    ]
    shown, snapshot = assemble_full_practice(quizzes, sources, lessons)
    assert len(shown) == 30
    assert snapshot["quotas"]["warfighting"] == 10
    ids = {row["quiz_id"] for row in shown}
    assert not any(quiz_id.startswith("afo-") for quiz_id in ids)
    assert sum(1 for quiz_id in ids if quiz_id.startswith("wf-")) == 10
    assert sum(1 for quiz_id in ids if quiz_id.startswith("nav-")) == 10


def test_eligible_quizzes_skip_empty_stems() -> None:
    rows = eligible_quizzes(
        [
            _quiz("ok", source_id="src"),
            {"id": "bad", "question": " ", "options": ["A", "B"], "answer_pool": {}},
        ]
    )
    assert [row["id"] for row in rows] == ["ok"]
