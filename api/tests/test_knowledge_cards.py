import asyncio

import pytest

from app.config import get_settings
from app.knowledge.cards import entries_in_category, flashcard_sides, layout_needs_image
from app.qngen.canonical_context import ConceptCard
from app.qngen.skills.shared.orchestrator import run_skill_batch
from app.qngen.stages.models import QuizGenOutput
from app.services.knowledge_projects import KnowledgeProjectService


def test_flashcard_layouts() -> None:
    entry = {
        "preferred_label": "Friction",
        "definition": "The collective force that resists all action.",
        "significance": "The primary operational obstacle.",
    }

    assert flashcard_sides(entry, "label_description") == (
        "Friction",
        "The collective force that resists all action.\n\nThe primary operational obstacle.",
    )
    assert flashcard_sides(entry, "image_label") == ("Friction", "Friction")
    assert flashcard_sides(entry, "image_label_description")[0] == "Friction"
    assert layout_needs_image("label_description") is False
    assert layout_needs_image("image_label") is True
    assert layout_needs_image("image_label_description") is True


def test_category_batch_keeps_only_that_category() -> None:
    entries = [
        {"id": "war", "category": "Nature of War"},
        {"id": "friction", "category": "Characteristics of War"},
        {"id": "blank", "category": None},
    ]

    assert [entry["id"] for entry in entries_in_category(entries, "Nature of War")] == ["war"]
    assert [entry["id"] for entry in entries_in_category(entries, "Uncategorized")] == ["blank"]


class _PromptClient:
    provider = "openai"
    model = "fake"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None):
        del system_prompt, model
        self.prompts.append(user_prompt)

        class _Result:
            content = {
                "items": [
                    {
                        "type": "quiz",
                        "subtype": "multiple_choice",
                        "question": "What is friction?",
                        "choices": ["Resistance", "Tempo"],
                        "correct_answer": "Resistance",
                        "wiki_ids_cited": ["wiki-friction"],
                        "source_chunk_ids": [],
                    },
                ],
            }
            model = "fake"
            provider = "openai"
            token_usage = {}

        return _Result()


def test_question_batch_prompt_includes_the_instruction_and_format() -> None:
    client = _PromptClient()
    concept = ConceptCard(
        wiki_id="wiki-friction",
        preferred_label="Friction",
        definition="Resistance.",
        importance="contextual",
    )

    run_skill_batch(
        skill_name="questions",
        artifact_type="quiz",
        source_metadata={"title": "Chapter 1"},
        concepts=[concept],
        learning_objectives=[],
        instructions="Ask about the fog of war.",
        required_subtype="multiple_choice",
        draft_client=client,
        critique_client=client,
    )

    assert len(client.prompts) == 1
    assert "Ask about the fog of war." in client.prompts[0]
    assert 'subtype "multiple_choice"' in client.prompts[0]


def test_generate_batch_sends_only_the_category(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[ConceptCard]] = []

    class _Stage:
        def run(self, **kwargs):
            captured.append(kwargs["concepts"])
            return QuizGenOutput(questions=[]), {}

    monkeypatch.setattr("app.services.knowledge_projects.QuizGenStage", _Stage)

    class _Projects:
        async def list_plans(self, project_id: str) -> list[dict]:
            del project_id
            return [
                {"item_type": "flashcard", "wiki_entry_id": "war"},
                {"item_type": "flashcard", "wiki_entry_id": "friction"},
            ]

        async def list_assessments(self, table: str, project_id: str) -> list[dict]:
            del table, project_id
            return []

    class _Wiki:
        async def get_many(self, ids: list[str]) -> list[dict]:
            del ids
            return [
                {"id": "war", "preferred_label": "War", "definition": "A clash.", "category": "Nature of War", "importance": "supporting", "entry_kind": "term"},
                {"id": "friction", "preferred_label": "Friction", "definition": "Resistance.", "category": "Characteristics of War", "importance": "supporting", "entry_kind": "term"},
            ]

    service = KnowledgeProjectService(
        projects=_Projects(),
        production_runs=object(),
        batches=object(),
        wiki_entries=_Wiki(),
        settings=get_settings(),
    )

    with pytest.raises(Exception, match="No questions"):
        asyncio.run(service.generate_batch(
            {"id": "project-1", "status": "composing", "title": "Chapter 1", "workspace_id": "ws-1", "source_id": "book-1"},
            kind="question",
            category="Nature of War",
            item_format="multiple_choice",
            instructions="Stay with definitions.",
        ))

    assert [concept.wiki_id for concept in captured[0]] == ["war"]


def _project() -> dict:
    return {
        "id": "project-1",
        "status": "composing",
        "title": "Chapter 1",
        "workspace_id": "ws-1",
        "source_id": "book-1",
        "batch_instructions": {"Characteristics of War": "Stay in the field."},
    }


def _entries() -> list[dict]:
    return [
        {
            "id": "friction",
            "preferred_label": "Friction",
            "definition": "Resistance.",
            "category": "Characteristics of War",
            "importance": "supporting",
            "entry_kind": "term",
        },
        {
            "id": "chance",
            "preferred_label": "Chance",
            "definition": "Luck.",
            "category": "Characteristics of War",
            "importance": "supporting",
            "entry_kind": "term",
        },
    ]


class _RecordingProjects:
    def __init__(self, assessments: list[dict] | None = None) -> None:
        self.assessments = assessments or []
        self.deleted: list[tuple[str, list[str]]] = []
        self.inserted: list[dict] = []
        self.plans: list[dict] = []
        self.updated_rows: list[tuple[str, str, dict]] = []
        self.updated_plans: list[tuple[str, dict]] = []

    async def list_plans(self, project_id: str) -> list[dict]:
        del project_id
        return [
            {"id": "plan-friction", "item_type": "flashcard", "wiki_entry_id": "friction", "instructions": "Ask for a contrast."},
            {"id": "plan-chance", "item_type": "flashcard", "wiki_entry_id": "chance"},
        ]

    async def list_assessments(self, table: str, project_id: str) -> list[dict]:
        del table, project_id
        return self.assessments

    async def delete_rows(self, table: str, row_ids: list[str]) -> None:
        self.deleted.append((table, row_ids))

    async def insert_rows(self, table: str, rows: list[dict]) -> list[dict]:
        del table
        saved = [{**row, "id": f"saved-{len(self.inserted) + index}"} for index, row in enumerate(rows)]
        self.inserted.extend(saved)
        return saved

    async def insert_plans(self, rows: list[dict]) -> list[dict]:
        self.plans.extend(rows)
        return rows

    async def update_row(self, table: str, row_id: str, payload: dict) -> dict:
        self.updated_rows.append((table, row_id, payload))
        return payload

    async def update_plan(self, plan_id: str, payload: dict) -> dict:
        self.updated_plans.append((plan_id, payload))
        return payload


class _WikiEntries:
    async def get_many(self, ids: list[str]) -> list[dict]:
        del ids
        return _entries()


class _QuestionStage:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        from app.qngen.stages.models import GeneratedQuizQuestion

        question = GeneratedQuizQuestion(
            question=f"Question {len(self.calls)}",
            correct_answer="Friction",
            options=["Friction", "Chance"],
            wiki_ids_cited=["friction"],
        )
        return QuizGenOutput(questions=[question]), {}


def _service(projects: _RecordingProjects) -> KnowledgeProjectService:
    return KnowledgeProjectService(
        projects=projects,
        production_runs=object(),
        batches=object(),
        wiki_entries=_WikiEntries(),
        settings=get_settings(),
    )


def test_generate_variants_offers_siblings_and_skips_asked_stems(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = _QuestionStage()
    monkeypatch.setattr("app.services.knowledge_projects.QuizGenStage", lambda: stage)
    projects = _RecordingProjects(
        [{"id": "old", "question": "What is friction?", "citations": [{"uri": "wiki://friction"}]}],
    )

    asyncio.run(
        _service(projects).generate_variants(
            _project(),
            wiki_entry_id="friction",
            kind="question",
            item_format="multiple_choice",
            count=1,
            mix="same",
            bloom_level="understand",
            instructions="Use a contrast.",
        ),
    )

    call = stage.calls[0]
    assert [concept.wiki_id for concept in call["concepts"]] == ["friction"]
    assert [concept.wiki_id for concept in call["context_concepts"]] == ["chance"]
    assert call["avoid_stems"] == ["What is friction?"]
    assert call["bloom_level"] == "understand"
    assert "Ask for a contrast." in call["instructions"]
    assert "Stay in the field." in call["instructions"]
    assert projects.inserted[0]["answer_pool"] == {} or "correct" in projects.inserted[0]["answer_pool"]
    assert projects.plans[0]["wiki_entry_id"] == "friction"
    assert projects.deleted == []


def test_spread_rotates_format_and_bloom(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = _QuestionStage()
    monkeypatch.setattr("app.services.knowledge_projects.QuizGenStage", lambda: stage)

    asyncio.run(
        _service(_RecordingProjects()).generate_variants(
            _project(),
            wiki_entry_id="friction",
            kind="question",
            item_format="multiple_choice",
            count=2,
            mix="spread",
        ),
    )

    assert [call["required_subtype"] for call in stage.calls] == ["multiple_choice", "true_false_correction"]
    assert [call["bloom_level"] for call in stage.calls] == ["remember", "understand"]
    assert stage.calls[1]["avoid_stems"] == ["Question 1"]


def test_generate_batch_append_keeps_rows_and_replace_removes_them(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = _QuestionStage()
    monkeypatch.setattr("app.services.knowledge_projects.QuizGenStage", lambda: stage)
    existing = [{"id": "old", "question": "Already asked", "citations": [{"uri": "wiki://friction"}]}]
    projects = _RecordingProjects(existing)

    asyncio.run(
        _service(projects).generate_batch(
            _project(),
            kind="question",
            category="Characteristics of War",
            item_format="multiple_choice",
            instructions="",
            per_entry=2,
            mode="append",
        ),
    )

    assert projects.deleted == []
    assert stage.calls[0]["items_per_concept"] == 2
    assert "Already asked" in stage.calls[0]["avoid_stems"]
    assert {concept.wiki_id for concept in stage.calls[0]["concepts"]} == {"friction", "chance"}

    asyncio.run(
        _service(projects).generate_batch(
            _project(),
            kind="question",
            category="Characteristics of War",
            item_format="multiple_choice",
            instructions="",
            mode="replace",
        ),
    )

    assert ("quizzes", ["old"]) in projects.deleted


def test_save_item_writes_the_pool_and_clears_the_draft() -> None:
    projects = _RecordingProjects()

    asyncio.run(
        _service(projects).save_item(
            _project(),
            {"id": "plan-q", "item_type": "question", "assessment_id": "quiz-1"},
            kind="question",
            payload={
                "question": "What resists action?",
                "format": "multiple_choice",
                "answer_pool": {
                    "correct": ["Friction"],
                    "distractors": [{"text": "Chance", "misconception": "A different characteristic."}],
                    "show_count": 2,
                },
                "explanation": "Friction is the resistance.",
                "difficulty": "medium",
                "bloom_level": "remember",
            },
        ),
    )

    table, row_id, changes = projects.updated_rows[0]
    assert table == "quizzes"
    assert row_id == "quiz-1"
    assert changes["answer_pool"]["correct"] == ["Friction"]
    assert set(changes["options"]) == {"Friction", "Chance"}
    assert changes["correct_answer"] == "Friction"
    assert projects.updated_plans == [("plan-q", {"draft": None})]


def test_duplicate_item_copies_the_saved_question() -> None:
    projects = _RecordingProjects(
        [
            {
                "id": "quiz-1",
                "question": "What resists action?",
                "correct_answer": "Friction",
                "options": ["Friction", "Chance"],
                "answer_pool": {"correct": ["Friction"], "distractors": [], "show_count": 2},
                "citations": [{"uri": "wiki://friction"}],
                "created_at": "2026-01-01T00:00:00Z",
            },
        ],
    )

    asyncio.run(
        _service(projects).duplicate_item(
            _project(),
            {"id": "plan-q", "item_type": "question", "assessment_id": "quiz-1", "wiki_entry_id": "friction"},
        ),
    )

    assert projects.inserted[0]["id"] == "saved-0"
    assert "created_at" not in projects.inserted[0]
    assert projects.inserted[0]["question"] == "What resists action?"
    assert projects.plans[0]["wiki_entry_id"] == "friction"
    assert projects.plans[0]["assessment_id"] == "saved-0"


def test_variant_prompt_names_the_level_the_avoided_stems_and_the_siblings() -> None:
    client = _PromptClient()
    sibling = ConceptCard(wiki_id="wiki-chance", preferred_label="Chance", definition="Luck.", importance="contextual")

    run_skill_batch(
        skill_name="questions",
        artifact_type="quiz",
        source_metadata={"title": "Chapter 1"},
        concepts=[
            ConceptCard(wiki_id="wiki-friction", preferred_label="Friction", definition="Resistance.", importance="contextual"),
        ],
        learning_objectives=[],
        bloom_level="apply",
        items_per_concept=2,
        avoid_stems=["What is friction?"],
        context_concepts=[sibling],
        draft_client=client,
        critique_client=client,
    )

    prompt = client.prompts[0]
    assert "Target cognitive level: apply" in prompt
    assert "exactly 2" in prompt
    assert "What is friction?" in prompt
    assert "Distractor candidates" in prompt
    assert "Chance" in prompt
