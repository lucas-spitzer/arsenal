from __future__ import annotations

from typing import Any

from app.qngen.skills.shared.item_mapping import normalize_difficulty


def build_citations(
    *,
    wiki_ids: list[str],
    segment_ids: list[str],
    source_id: str,
) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []

    for wiki_id in wiki_ids:
        citations.append({"uri": f"wiki://{wiki_id}", "type": "wiki"})

    for segment_id in segment_ids:
        citations.append(
            {
                "uri": f"seg://{source_id}/{segment_id}",
                "type": "segment",
            },
        )

    return citations


def promote_flashcards(
    *,
    workspace_id: str,
    source_id: str,
    production_run_id: str,
    stage_run_id: str,
    stage_id: str,
    stage_version: str,
    flashcards: list[dict[str, Any]],
    knowledge_project_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for card in flashcards:
        rows.append(
            {
                "workspace_id": workspace_id,
                "source_id": source_id,
                "production_run_id": production_run_id,
                "stage_run_id": stage_run_id,
                "front": card["front"],
                "back": card["back"],
                "difficulty": normalize_difficulty(card.get("difficulty")),
                "tags": card.get("tags") or [],
                "citations": build_citations(
                    wiki_ids=card.get("wiki_ids_cited") or [],
                    segment_ids=card.get("segment_ids_used") or [],
                    source_id=source_id,
                ),
                "origin": {
                    "stage_run_id": stage_run_id,
                    "stage_id": stage_id,
                    "stage_version": stage_version,
                },
                **({"knowledge_project_id": knowledge_project_id} if knowledge_project_id else {}),
            },
        )

    return rows


def promote_quizzes(
    *,
    workspace_id: str,
    source_id: str,
    production_run_id: str,
    stage_run_id: str,
    stage_id: str,
    stage_version: str,
    questions: list[dict[str, Any]],
    knowledge_project_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for question in questions:
        rows.append(
            {
                "workspace_id": workspace_id,
                "source_id": source_id,
                "production_run_id": production_run_id,
                "stage_run_id": stage_run_id,
                "question": question["question"],
                "question_type": question.get("question_type") or "multiple_choice",
                "options": question.get("options") or [],
                "correct_answer": question["correct_answer"],
                "answer_pool": question.get("answer_pool") or {},
                "bloom_level": question.get("bloom_level"),
                "explanation": question.get("explanation"),
                "difficulty": normalize_difficulty(question.get("difficulty")),
                "citations": build_citations(
                    wiki_ids=question.get("wiki_ids_cited") or [],
                    segment_ids=question.get("segment_ids_used") or [],
                    source_id=source_id,
                ),
                "origin": {
                    "stage_run_id": stage_run_id,
                    "stage_id": stage_id,
                    "stage_version": stage_version,
                },
                **({"knowledge_project_id": knowledge_project_id} if knowledge_project_id else {}),
            },
        )

    return rows


def promote_scenarios(
    *,
    workspace_id: str,
    source_id: str,
    production_run_id: str,
    stage_run_id: str,
    stage_id: str,
    stage_version: str,
    scenarios: list[dict[str, Any]],
    knowledge_project_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for scenario in scenarios:
        rows.append(
            {
                "workspace_id": workspace_id,
                "source_id": source_id,
                "production_run_id": production_run_id,
                "stage_run_id": stage_run_id,
                "title": scenario["title"],
                "prompt": scenario["prompt"],
                "context": scenario.get("context"),
                "evaluation_criteria": scenario.get("evaluation_criteria") or [],
                "bloom_level": scenario.get("bloom_level"),
                "difficulty": normalize_difficulty(scenario.get("difficulty")),
                "citations": build_citations(
                    wiki_ids=scenario.get("wiki_ids_cited") or [],
                    segment_ids=scenario.get("segment_ids_used") or [],
                    source_id=source_id,
                ),
                "origin": {
                    "stage_run_id": stage_run_id,
                    "stage_id": stage_id,
                    "stage_version": stage_version,
                },
                **({"knowledge_project_id": knowledge_project_id} if knowledge_project_id else {}),
            },
        )

    return rows
