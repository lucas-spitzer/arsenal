import random
from datetime import UTC, datetime

from app.services.atlas_exams import (
    ExamAssemblyError,
    assemble_full_practice,
    assemble_subject_exam,
    eligible_quizzes,
)
from app.services.atlas_scoring import (
    leaderboard_stats,
    points_for_correct_answer,
    rank_movement,
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


CUTOFF = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
EARLY = "2026-11-24T08:00:00+00:00"
LATE = "2026-11-25T08:00:00Z"


def _standings(stats: dict[str, dict]) -> list[dict]:
    empty = {"lifetime_ap": 0, "concepts_mastered": 0, "accuracy": None}
    return [{"user_id": user_id, "name": user_id, **stats.get(user_id, empty)} for user_id in ("a", "b", "c")]


def _movement(events: list[dict]) -> dict[str, int]:
    current = leaderboard_stats(events, [], [])
    prior = leaderboard_stats(events, [], [], as_of=CUTOFF)
    return rank_movement(_standings(current), _standings(prior))


def test_late_points_move_a_student_up_and_others_down() -> None:
    movement = _movement(
        [
            {"user_id": "a", "points": 10, "created_at": EARLY},
            {"user_id": "b", "points": 5, "created_at": EARLY},
            {"user_id": "c", "points": 20, "created_at": LATE},
        ]
    )
    assert movement == {"c": 2, "a": -1, "b": -1}


def test_points_before_the_cutoff_do_not_count_as_movement() -> None:
    movement = _movement(
        [
            {"user_id": "a", "points": 10, "created_at": EARLY},
            {"user_id": "c", "points": 20, "created_at": EARLY},
        ]
    )
    assert movement == {"a": 0, "b": 0, "c": 0}


def test_late_points_that_keep_the_order_are_no_movement() -> None:
    movement = _movement(
        [
            {"user_id": "a", "points": 10, "created_at": EARLY},
            {"user_id": "a", "points": 5, "created_at": LATE},
            {"user_id": "b", "points": 3, "created_at": LATE},
        ]
    )
    assert movement == {"a": 0, "b": 0, "c": 0}


def test_stats_cutoff_applies_to_mastery_and_accuracy() -> None:
    progress = [
        {"user_id": "a", "mastered_at": EARLY},
        {"user_id": "a", "mastered_at": LATE},
        {"user_id": "a", "mastered_at": None},
    ]
    answers = [
        {"user_id": "a", "is_correct": True, "submitted_at": EARLY},
        {"user_id": "a", "is_correct": False, "submitted_at": LATE},
    ]
    assert leaderboard_stats([], progress, answers, as_of=CUTOFF)["a"] == {
        "lifetime_ap": 0,
        "concepts_mastered": 1,
        "accuracy": 100,
    }
    assert leaderboard_stats([], progress, answers)["a"]["accuracy"] == 50


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


FULL_SOURCES = [
    # Newest first, as the repository returns them.
    {"id": "src-1-4", "filename": "MCDP 1-4.pdf", "source_metadata": {}},
    {"id": "src-1-1", "filename": "MCDP 1-1.pdf", "source_metadata": {}},
    {"id": "src-wf", "filename": "MCDP 1 Warfighting.pdf", "source_metadata": {}},
    {"id": "src-afo", "filename": "Armed Forces Officer.pdf", "source_metadata": {}},
    {"id": "src-ops", "filename": "Ops.pdf", "source_metadata": {"display_name": "Operations"}},
]
FULL_LESSONS = [
    {"id": "les-nav", "title": "Land Navigation"},
    {"id": "les-uni", "title": "Uniforms, Customs, and Courtesies"},
    {"id": "les-tccc", "title": "Tactical Combat Casualty Care"},
    {"id": "les-comm", "title": "Communications Equipment"},
    {"id": "les-empty", "title": "Cardinal Virtues"},
]


def _full_quizzes(*, uniforms: int = 12) -> list[dict]:
    return [
        *[_quiz(f"wf-{i}", source_id="src-wf") for i in range(35)],
        *[_quiz(f"m14-{i}", source_id="src-1-4") for i in range(3)],
        *[_quiz(f"nav-{i}", lesson_id="les-nav") for i in range(20)],
        *[_quiz(f"afo-{i}", source_id="src-afo") for i in range(12)],
        *[_quiz(f"ops-{i}", source_id="src-ops") for i in range(12)],
        *[_quiz(f"uni-{i}", lesson_id="les-uni") for i in range(uniforms)],
        *[_quiz(f"tccc-{i}", lesson_id="les-tccc") for i in range(2)],
        *[_quiz(f"comm-{i}", lesson_id="les-comm") for i in range(1)],
    ]


def _count(ids: list[str], prefix: str) -> int:
    return sum(1 for quiz_id in ids if quiz_id.startswith(prefix))


def test_full_practice_draws_ten_five_fifteen_from_classes() -> None:
    shown, snapshot = assemble_full_practice(_full_quizzes(), FULL_SOURCES, FULL_LESSONS, rng=random.Random(7))
    ids = [row["quiz_id"] for row in shown]
    assert len(ids) == 30
    assert len(set(ids)) == 30
    assert snapshot["quotas"] == {"warfighting": 10, "land_navigation": 5, "other": 15}
    assert snapshot["warfighting_source_id"] == "src-wf"
    assert _count(ids, "wf-") == 10
    assert _count(ids, "nav-") == 5
    assert _count(ids, "uni-") + _count(ids, "tccc-") + _count(ids, "comm-") == 15
    assert _count(ids, "tccc-") >= 1
    assert _count(ids, "comm-") == 1
    for prefix in ("afo-", "ops-", "m14-"):
        assert _count(ids, prefix) == 0


def test_full_practice_ignores_other_mcdp_1_publications() -> None:
    sources = [
        {"id": "src-1-4", "filename": "MCDP 1-4.pdf", "source_metadata": {}},
        {"id": "src-1-2", "filename": "MCDP 1-2.pdf", "source_metadata": {}},
        {"id": "src-wf", "filename": "MCDP 1 Warfighting.pdf", "source_metadata": {}},
    ]
    quizzes = [q for q in _full_quizzes() if not q["id"].startswith("m14-")]
    _, snapshot = assemble_full_practice(quizzes, sources, FULL_LESSONS, rng=random.Random(1))
    assert snapshot["warfighting_source_id"] == "src-wf"


def test_full_practice_prefers_warfighting_match_with_most_questions() -> None:
    sources = [
        {"id": "src-short", "filename": "Warfighting.pdf", "source_metadata": {}},
        *FULL_SOURCES,
    ]
    quizzes = [*_full_quizzes(), _quiz("short-0", source_id="src-short")]
    _, snapshot = assemble_full_practice(quizzes, sources, FULL_LESSONS, rng=random.Random(2))
    assert snapshot["warfighting_source_id"] == "src-wf"


def test_full_practice_names_real_class_shortage() -> None:
    try:
        assemble_full_practice(_full_quizzes(uniforms=5), FULL_SOURCES, FULL_LESSONS)
        raise AssertionError("expected shortage")
    except ExamAssemblyError as exc:
        assert "15" in exc.detail
        assert "have 8" in exc.detail
        assert "Land Navigation" in exc.detail


def test_full_practice_shuffles_questions_and_options() -> None:
    shown, _ = assemble_full_practice(_full_quizzes(), FULL_SOURCES, FULL_LESSONS, rng=random.Random(11))
    subjects = [row["subject_id"] for row in shown]
    assert subjects[:10] != ["src-wf"] * 10
    assert subjects[10:15] != ["les-nav"] * 5
    assert all(sorted(row["options"]) == ["A", "B", "C", "D"] for row in shown)
    assert any(row["options"] != ["A", "B", "C", "D"] for row in shown)


def test_eligible_quizzes_skip_empty_stems() -> None:
    rows = eligible_quizzes(
        [
            _quiz("ok", source_id="src"),
            {"id": "bad", "question": " ", "options": ["A", "B"], "answer_pool": {}},
        ]
    )
    assert [row["id"] for row in rows] == ["ok"]


def test_eligible_quizzes_skip_short_answers() -> None:
    rows = eligible_quizzes(
        [
            _quiz("ok", source_id="src"),
            {
                "id": "short",
                "question": "What is friction?",
                "question_type": "short_answer",
                "subtype": "short_answer",
                "options": [],
                "correct_answer": "",
                "answer_pool": {},
                "evaluation_criteria": ["Names the force that resists action"],
            },
        ]
    )
    assert [row["id"] for row in rows] == ["ok"]
