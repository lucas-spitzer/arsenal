from app.services.short_answer_grading import parse_short_answer_grade


def test_parse_short_answer_grade_maps_payload() -> None:
    grade = parse_short_answer_grade(
        {
            "passed": True,
            "feedback": "Covers friction and its ubiquity.",
            "met_criteria": ["Names the force that resists action"],
            "missed_criteria": [],
        },
    )
    assert grade.passed is True
    assert grade.feedback == "Covers friction and its ubiquity."
    assert grade.met_criteria == ["Names the force that resists action"]
    assert grade.missed_criteria == []


def test_parse_short_answer_grade_defaults_missing_fields() -> None:
    grade = parse_short_answer_grade({})
    assert grade.passed is False
    assert grade.feedback == ""
    assert grade.met_criteria == []
    assert grade.missed_criteria == []
