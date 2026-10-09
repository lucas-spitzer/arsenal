from __future__ import annotations

from typing import Any

from app.qngen.canonical_context import ConceptCard, build_chapter_blueprint
from app.qngen.skills.questions.helpers import ensure_list_questions, normalize_quiz_items
from app.qngen.skills.shared.item_mapping import (
    assessment_item_to_quiz,
    ensure_item_ids,
)
from app.qngen.skills.shared.orchestrator import (
    run_blueprinted_generation,
    run_skill_generation,
)
from app.qngen.stages.models import GeneratedQuizQuestion, QuizGenOutput
from app.qngen.validators import validate_assessment_items


class QuizGenStage:
    def run(
        self,
        *,
        source_metadata: dict[str, Any],
        concepts: list[ConceptCard],
        concept_batches: list[list[ConceptCard]],
        learning_objectives: list[dict[str, Any]],
        chapters: list[dict[str, Any]] | None = None,
        skip_importance_filter: bool = False,
        instructions: str = "",
        required_subtype: str = "",
        bloom_level: str = "",
        items_per_concept: int | None = None,
        avoid_stems: list[str] | None = None,
        context_concepts: list[ConceptCard] | None = None,
    ) -> tuple[QuizGenOutput, dict[str, Any]]:
        # Shared with the flashcard and scenario stages so one caller can pass the flag.
        _ = skip_importance_filter
        blueprint = build_chapter_blueprint(chapters or [], concepts)

        raw_items: list[dict[str, Any]] = []
        execution: dict[str, Any] = {}
        if blueprint:
            # One question per objective, scoped per chapter (no count band —
            # questions are deterministically objective-driven).
            raw_items, execution = run_blueprinted_generation(
                skill_name="questions",
                artifact_type="quiz",
                source_metadata=source_metadata,
                blueprint=blueprint,
            )

        if not raw_items:
            # No chapter structure, or the chapter↔concept join produced nothing
            # (e.g. orphan evidence segments): fall back to the concept-fan-out
            # path so a missing/broken blueprint can't silently zero out output.
            if not concept_batches:
                raise RuntimeError(
                    "At least one concept batch is required for quiz generation.",
                )
            raw_items, execution = run_skill_generation(
                skill_name="questions",
                artifact_type="quiz",
                source_metadata=source_metadata,
                concept_batches=concept_batches,
                learning_objectives=learning_objectives,
                instructions=instructions,
                required_subtype=required_subtype,
                bloom_level=bloom_level,
                items_per_concept=items_per_concept,
                avoid_stems=avoid_stems,
                context_concepts=context_concepts,
            )

        raw_items = ensure_list_questions(
            normalize_quiz_items(ensure_item_ids(raw_items)),
            concepts,
        )

        wiki_ids = {concept.wiki_id for concept in concepts}
        segment_ids = {
            segment_id
            for concept in concepts
            for segment_id in concept.evidence_segment_ids
        }

        validated, validation_report = validate_assessment_items(
            items=raw_items,
            concepts=concepts,
            segment_ids=segment_ids,
            wiki_ids=wiki_ids,
            max_per_concept=items_per_concept,
        )
        questions = [
            GeneratedQuizQuestion.model_validate(assessment_item_to_quiz(item))
            for item in validated
            if item.get("type") == "quiz"
        ]

        execution["validation_report"] = validation_report
        return QuizGenOutput(questions=questions), execution
