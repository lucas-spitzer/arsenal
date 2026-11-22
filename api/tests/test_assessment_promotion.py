from app.qngen.assessment_promotion import (
    build_citations,
    promote_flashcards,
    promote_quizzes,
    promote_scenarios,
)


def test_build_citations() -> None:
    citations = build_citations(
        wiki_ids=["wiki-1"],
        segment_ids=["seg-1"],
        source_id="src-1",
    )

    assert citations == [
        {"uri": "wiki://wiki-1", "type": "wiki"},
        {"uri": "seg://src-1/seg-1", "type": "segment"},
    ]


def test_promote_flashcards_maps_rows() -> None:
    rows = promote_flashcards(
        workspace_id="ws-1",
        source_id="src-1",
        production_run_id="run-1",
        stage_run_id="stage-1",
        stage_id="generate-flashcards",
        stage_version="1.0",
        flashcards=[
            {
                "front": "What is METT-T?",
                "back": "Mission, Enemy, Terrain, Troops, Time.",
                "difficulty": "medium",
                "tags": ["doctrine"],
                "wiki_ids_cited": ["wiki-1"],
                "segment_ids_used": ["seg-1"],
            },
        ],
    )

    assert len(rows) == 1
    assert rows[0]["front"] == "What is METT-T?"
    assert rows[0]["origin"]["stage_id"] == "generate-flashcards"


def test_promote_quizzes_maps_rows() -> None:
    rows = promote_quizzes(
        workspace_id="ws-1",
        source_id="src-1",
        production_run_id="run-1",
        stage_run_id="stage-1",
        stage_id="generate-questions",
        stage_version="1.0",
        questions=[
            {
                "question": "Which factor is part of METT-T?",
                "question_type": "multiple_choice",
                "options": ["Enemy", "Budget", "Payroll", "Marketing"],
                "correct_answer": "Enemy",
                "difficulty": "easy",
            },
        ],
    )

    assert rows[0]["question_type"] == "multiple_choice"
    assert "source" not in rows[0]["origin"]


def test_promote_quizzes_tags_knowledge_project_as_wiki_term() -> None:
    rows = promote_quizzes(
        workspace_id="ws-1",
        source_id="src-1",
        production_run_id="run-1",
        stage_run_id="stage-1",
        stage_id="generate-questions",
        stage_version="1.0",
        knowledge_project_id="project-1",
        questions=[
            {
                "question": "Which factor is part of METT-T?",
                "question_type": "multiple_choice",
                "options": ["Enemy", "Budget", "Payroll", "Marketing"],
                "correct_answer": "Enemy",
                "difficulty": "easy",
            },
        ],
    )

    assert rows[0]["knowledge_project_id"] == "project-1"
    assert rows[0]["origin"]["source"] == "wiki_term"
    assert rows[0]["origin"]["stage_id"] == "generate-questions"


def test_promote_scenarios_maps_rows() -> None:
    rows = promote_scenarios(
        workspace_id="ws-1",
        source_id="src-1",
        production_run_id="run-1",
        stage_run_id="stage-1",
        stage_id="generate-scenarios",
        stage_version="1.0",
        scenarios=[
            {
                "title": "Urban patrol decision",
                "prompt": "Choose your course of action.",
                "evaluation_criteria": ["Uses METT-T"],
                "difficulty": "hard",
            },
        ],
    )

    assert rows[0]["title"] == "Urban patrol decision"
