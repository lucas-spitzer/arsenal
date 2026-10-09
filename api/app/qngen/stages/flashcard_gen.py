from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.qngen.canonical_context import ConceptCard, build_chapter_blueprint
from app.qngen.skills.flashcards.helpers import ensure_list_flashcards, prefer_term_definition
from app.qngen.skills.shared.item_mapping import (
    assessment_item_to_flashcard,
    ensure_item_ids,
)
from app.qngen.skills.shared.orchestrator import (
    run_blueprinted_generation,
    run_skill_generation,
)
from app.qngen.stages.models import FlashcardGenOutput, GeneratedFlashcard
from app.qngen.validators import validate_assessment_items

_FLASHCARD_IMPORTANCE = {"essential", "supporting"}


class FlashcardGenStage:
    def run(
        self,
        *,
        source_metadata: dict[str, Any],
        concepts: list[ConceptCard],
        concept_batches: list[list[ConceptCard]],
        learning_objectives: list[dict[str, Any]],
        chapters: list[dict[str, Any]] | None = None,
        skip_importance_filter: bool = False,
    ) -> tuple[FlashcardGenOutput, dict[str, Any]]:
        blueprint = build_chapter_blueprint(chapters or [], concepts)

        raw_items: list[dict[str, Any]] = []
        execution: dict[str, Any] = {}
        if blueprint:
            settings = get_settings()
            raw_items, execution = run_blueprinted_generation(
                skill_name="flashcards",
                artifact_type="flashcard",
                source_metadata=source_metadata,
                blueprint=blueprint,
                concept_filter=None
                if skip_importance_filter
                else (lambda concept: concept.importance in _FLASHCARD_IMPORTANCE),
                count_band=(
                    settings.qngen.flashcards_per_chapter_min,
                    settings.qngen.flashcards_per_chapter_max,
                ),
            )

        if not raw_items:
            # No chapter structure, or the chapter↔concept join produced nothing
            # (e.g. orphan evidence segments): fall back to the concept-fan-out
            # path so a missing/broken blueprint can't silently zero out output.
            if not concept_batches:
                raise RuntimeError(
                    "At least one concept batch is required for flashcard generation.",
                )
            raw_items, execution = run_skill_generation(
                skill_name="flashcards",
                artifact_type="flashcard",
                source_metadata=source_metadata,
                concept_batches=concept_batches,
                learning_objectives=learning_objectives,
            )

        raw_items = prefer_term_definition(
            ensure_list_flashcards(ensure_item_ids(raw_items), concepts),
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
        )
        flashcards = [
            GeneratedFlashcard.model_validate(assessment_item_to_flashcard(item))
            for item in validated
            if item.get("type") == "flashcard"
        ]

        execution["validation_report"] = validation_report
        return FlashcardGenOutput(flashcards=flashcards), execution
