from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.qngen.canonical_context import ConceptCard
from app.qngen.skills.shared.item_mapping import (
    assessment_item_to_flashcard,
    assessment_item_to_quiz,
    assessment_item_to_scenario,
    normalize_question_type,
)
from app.qngen.skills.shared.orchestrator import run_skill_batch
from app.qngen.stages.flashcard_gen import FlashcardGenStage
from app.services.llm.base import LLMCompletionResult


class FakeLLMClient:
    provider = "anthropic"
    model = "claude-test"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None):
        content = self.responses[self.calls]
        self.calls += 1
        return LLMCompletionResult(
            content=content,
            model=self.model,
            provider=self.provider,
            token_usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        )


def _concept(wiki_id: str, label: str, *, importance: str = "essential") -> ConceptCard:
    return ConceptCard(
        wiki_id=wiki_id,
        preferred_label=label,
        definition=f"Definition for {label}",
        importance=importance,
        evidence_segment_ids=["seg-1"],
        evidence_segments=[
            {"segment_id": "seg-1", "kind": "paragraph", "text": "Evidence text.", "page": 1},
        ],
    )


def test_normalize_question_type_maps_subtypes() -> None:
    assert normalize_question_type("true_false_correction") == "true_false"
    assert normalize_question_type("multiple_select") == "multiple_select"


def test_assessment_item_mapping() -> None:
    flashcard = assessment_item_to_flashcard(
        {
            "front": "Alpha",
            "back": "Definition",
            "wiki_ids_cited": ["w1"],
            "source_chunk_ids": ["seg-1"],
        },
    )
    quiz = assessment_item_to_quiz(
        {
            "question": "Q?",
            "subtype": "multiple_select",
            "choices": ["A", "B"],
            "correct_answer": "A; B",
            "wiki_ids_cited": ["w1"],
            "source_chunk_ids": ["seg-1"],
        },
    )
    scenario = assessment_item_to_scenario(
        {
            "task": "Apply Alpha",
            "situation": "Context",
            "wiki_ids_cited": ["w1"],
            "source_chunk_ids": ["seg-1"],
        },
    )

    assert flashcard["segment_ids_used"] == ["seg-1"]
    assert quiz["question_type"] == "multiple_select"
    assert scenario["prompt"] == "Apply Alpha"


def test_run_skill_batch_draft_only_for_contextual() -> None:
    draft = FakeLLMClient(
        [
            {
                "items": [
                    {
                        "item_id": "fc-1",
                        "type": "flashcard",
                        "front": "Alpha",
                        "back": "Definition for Alpha",
                        "wiki_ids_cited": ["wiki-1"],
                        "source_chunk_ids": ["seg-1"],
                    },
                ],
            },
        ],
    )

    items, execution = run_skill_batch(
        skill_name="flashcards",
        artifact_type="flashcard",
        source_metadata={},
        concepts=[_concept("wiki-1", "Alpha", importance="contextual")],
        learning_objectives=[],
        draft_client=draft,
        critique_client=draft,
    )

    assert draft.calls == 1
    assert len(items) == 1
    assert execution["provider"] == "anthropic"


def test_run_skill_batch_critique_and_revise_for_essential() -> None:
    draft = FakeLLMClient(
        [
            {
                "items": [
                    {
                        "item_id": "fc-1",
                        "type": "flashcard",
                        "front": "Alpha",
                        "back": "Weak",
                        "wiki_ids_cited": ["wiki-1"],
                        "source_chunk_ids": ["seg-1"],
                    },
                ],
            },
            {
                "items": [
                    {
                        "item_id": "fc-1",
                        "type": "flashcard",
                        "front": "Alpha",
                        "back": "Definition for Alpha",
                        "wiki_ids_cited": ["wiki-1"],
                        "source_chunk_ids": ["seg-1"],
                    },
                ],
            },
        ],
    )
    critique = FakeLLMClient(
        [
            {
                "issues": [{"item_id": "fc-1", "severity": "high", "issue": "weak back"}],
                "overall_quality": "needs_revision",
                "summary": "revise",
            },
        ],
    )

    items, execution = run_skill_batch(
        skill_name="flashcards",
        artifact_type="flashcard",
        source_metadata={},
        concepts=[_concept("wiki-1", "Alpha")],
        learning_objectives=[],
        draft_client=draft,
        critique_client=critique,
    )

    assert draft.calls == 2
    assert critique.calls == 1
    assert items[0]["back"] == "Definition for Alpha"
    assert execution["token_usage"]["total_tokens"] == 90


def test_flashcard_gen_stage_validates_and_maps() -> None:
    from unittest.mock import patch

    stage = FlashcardGenStage()

    with pytest.raises(RuntimeError, match="concept batch"):
        stage.run(
            source_metadata={},
            concepts=[],
            concept_batches=[],
            learning_objectives=[],
        )

    with patch(
        "app.qngen.stages.flashcard_gen.run_skill_generation",
        return_value=(
            [
                {
                    "item_id": "fc-1",
                    "type": "flashcard",
                    "front": "Alpha",
                    "back": "Definition for Alpha",
                    "wiki_ids_cited": ["wiki-1"],
                    "source_chunk_ids": ["seg-1"],
                },
            ],
            {
                "model": "claude-test",
                "provider": "anthropic",
                "token_usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            },
        ),
    ):
        output, execution = stage.run(
            source_metadata={},
            concepts=[_concept("wiki-1", "Alpha")],
            concept_batches=[[_concept("wiki-1", "Alpha")]],
            learning_objectives=[],
        )

    assert len(output.flashcards) == 1
    assert output.flashcards[0].front == "Alpha"
    assert execution["provider"] == "anthropic"
