from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings
from app.knowledge.plans import flashcard_enabled_by_default, study_wiki_ids, visual_updates_for_rows
from app.pipeline import build_knowledge_draft_pipeline
from app.services.knowledge_projects import KnowledgeProjectService
from app.worker.knowledge_runner import KnowledgeRunner


def test_flashcard_defaults_follow_kind_and_importance() -> None:
    assert flashcard_enabled_by_default({"entry_kind": "term", "importance": "essential"})
    assert flashcard_enabled_by_default({"entry_kind": "list", "importance": "supporting"})
    assert not flashcard_enabled_by_default({"entry_kind": "insight", "importance": "essential"})
    assert not flashcard_enabled_by_default({"entry_kind": "term", "importance": "contextual"})


def test_checked_list_pulls_component_terms_into_the_draft() -> None:
    plans = [
        {"item_type": "flashcard", "wiki_entry_id": "list-1", "enabled": True},
        {"item_type": "flashcard", "wiki_entry_id": "term-friction", "enabled": False},
        {"item_type": "flashcard", "wiki_entry_id": "term-other", "enabled": False},
    ]
    entries = [
        {
            "id": "list-1",
            "entry_kind": "list",
            "preferred_label": "Forms of Friction",
            "items": [{"name": "Friction", "details": "Resistance."}],
        },
        {"id": "term-friction", "entry_kind": "term", "preferred_label": "Friction", "items": []},
        {"id": "term-other", "entry_kind": "term", "preferred_label": "Tempo", "items": []},
    ]

    assert study_wiki_ids(plans, entries) == {"list-1", "term-friction"}


def test_draft_pipeline_includes_only_requested_stages() -> None:
    steps = [step["step"] for step in build_knowledge_draft_pipeline(flashcards=True, questions=False, scenarios=True)]

    assert steps == ["generate-flashcards", "generate-scenarios", "attach-visuals"]


def test_visual_updates_skip_plans_without_a_file() -> None:
    plans = [
        {
            "id": "plan-with-file",
            "item_type": "flashcard",
            "wiki_entry_id": "wiki-1",
            "visual": {"storage_path": "ws/knowledge/p/visuals/plan-with-file/map.png", "kind": "diagram"},
        },
        {
            "id": "plan-empty",
            "item_type": "flashcard",
            "wiki_entry_id": "wiki-2",
            "visual": None,
        },
    ]
    rows = [
        {"id": "card-1", "citations": [{"uri": "wiki://wiki-1"}]},
        {"id": "card-2", "citations": [{"uri": "wiki://wiki-2"}]},
    ]

    updates = visual_updates_for_rows(plans, rows, item_type="flashcard")

    assert [update[0] for update in updates] == ["card-1"]


class _MemoryDb:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.projects: dict[str, dict[str, Any]] = {}
        self.plans: list[dict[str, Any]] = []
        self.assessments: dict[str, list[dict[str, Any]]] = {"flashcards": [], "quizzes": [], "scenarios": []}
        self.deleted_projects: list[str] = []
        self.deleted_plan_types: list[list[str]] = []
        self.cleared: list[str] = []

    def get_wiki_entries(self, wiki_entry_ids: list[str]) -> list[dict[str, Any]]:
        return []

    def get_production_run(self, production_run_id: str) -> dict[str, Any] | None:
        return self.runs.get(production_run_id)

    def update_production_run(self, production_run_id: str, changes: dict[str, Any]) -> None:
        self.runs[production_run_id].update(changes)

    def sum_stage_run_costs(self, production_run_id: str) -> float:
        return 0.0

    def get_knowledge_project_for_run(self, production_run_id: str, column: str) -> dict[str, Any] | None:
        for project in self.projects.values():
            if project.get(column) == production_run_id:
                return project
        return None

    def update_knowledge_project(self, project_id: str, changes: dict[str, Any]) -> None:
        self.projects[project_id].update(changes)

    def get_sources(self, source_ids: list[str]) -> list[dict[str, Any]]:
        return [{"id": source_id, "title": "Book"} for source_id in source_ids]

    def list_knowledge_item_plans(self, project_id: str) -> list[dict[str, Any]]:
        return [plan for plan in self.plans if plan["knowledge_project_id"] == project_id]

    def delete_assessments_for_project(self, project_id: str) -> None:
        self.deleted_projects.append(project_id)
        for table in self.assessments:
            self.assessments[table] = []

    def delete_knowledge_item_plans(self, project_id: str, item_types: list[str]) -> None:
        self.deleted_plan_types.append(item_types)
        self.plans = [
            plan
            for plan in self.plans
            if plan["knowledge_project_id"] != project_id or plan["item_type"] not in item_types
        ]

    def clear_plan_assessments(self, project_id: str, item_type: str) -> None:
        self.cleared.append(item_type)
        for plan in self.plans:
            if plan["knowledge_project_id"] == project_id and plan["item_type"] == item_type:
                plan["assessment_id"] = None

    def list_assessments_for_project(self, table: str, project_id: str) -> list[dict[str, Any]]:
        return [row for row in self.assessments[table] if row.get("knowledge_project_id") == project_id]

    def update_knowledge_item_plan(self, plan_id: str, changes: dict[str, Any]) -> None:
        for plan in self.plans:
            if plan["id"] == plan_id:
                plan.update(changes)

    def update_assessment(self, table: str, assessment_id: str, changes: dict[str, Any]) -> None:
        for row in self.assessments[table]:
            if row["id"] == assessment_id:
                row.update(changes)

    def insert_knowledge_item_plans(self, rows: list[dict[str, Any]]) -> None:
        self.plans.extend(rows)


class _Stage:
    def __init__(self, db: _MemoryDb, *, table: str | None = None, row: dict[str, Any] | None = None) -> None:
        self.db = db
        self.table = table
        self.row = row
        self.calls: list[dict[str, Any]] = []

    def run_for_source(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        if self.table and self.row:
            self.db.assessments[self.table].append(dict(self.row))
        return "stage-run"


def test_draft_replaces_project_items_and_scopes_enabled_entries() -> None:
    db = _MemoryDb()
    db.runs["run-1"] = {
        "id": "run-1",
        "pipeline": build_knowledge_draft_pipeline(flashcards=True, questions=False, scenarios=False),
    }
    db.projects["project-1"] = {
        "id": "project-1",
        "workspace_id": "ws-1",
        "source_id": "source-1",
        "draft_run_id": "run-1",
        "draft_questions": False,
        "draft_scenarios": False,
    }
    db.plans = [
        {
            "id": "plan-on",
            "knowledge_project_id": "project-1",
            "wiki_entry_id": "wiki-on",
            "item_type": "flashcard",
            "enabled": True,
            "assessment_id": "old-card",
            "visual": {"storage_path": "ws/knowledge/project-1/visuals/plan-on/icon.png", "kind": "icon", "placement": "back"},
        },
        {
            "id": "plan-off",
            "knowledge_project_id": "project-1",
            "wiki_entry_id": "wiki-off",
            "item_type": "flashcard",
            "enabled": False,
            "visual": None,
        },
        {
            "id": "plan-question",
            "knowledge_project_id": "project-1",
            "wiki_entry_id": None,
            "item_type": "question",
            "enabled": True,
            "assessment_id": "old-quiz",
            "visual": None,
        },
    ]
    db.assessments["flashcards"] = [{"id": "old-card", "knowledge_project_id": "project-1"}]
    flashcards = _Stage(
        db,
        table="flashcards",
        row={
            "id": "new-card",
            "knowledge_project_id": "project-1",
            "citations": [{"uri": "wiki://wiki-on"}],
        },
    )
    questions = _Stage(db)
    runner = KnowledgeRunner(db=db, flashcards=flashcards, questions=questions, scenarios=_Stage(db))

    result = runner.draft("run-1")

    assert result["status"] == "completed"
    assert db.deleted_projects == ["project-1"]
    assert db.deleted_plan_types == [["question", "scenario"]]
    assert db.cleared == ["flashcard"]
    assert flashcards.calls[0]["wiki_ids"] == {"wiki-on"}
    assert flashcards.calls[0]["skip_importance_filter"] is True
    assert questions.calls == []
    linked = next(plan for plan in db.plans if plan["id"] == "plan-on")
    assert linked["assessment_id"] == "new-card"
    attached = next(row for row in db.assessments["flashcards"] if row["id"] == "new-card")
    assert attached["visual"]["storage_path"].endswith("icon.png")
    assert db.projects["project-1"]["status"] == "ready"
    assert not any(plan["item_type"] == "question" for plan in db.plans)


def test_attach_skips_a_plan_without_a_file_and_clears_a_removed_image() -> None:
    db = _MemoryDb()
    db.runs["run-2"] = {"id": "run-2", "pipeline": [{"step": "attach-visuals", "status": "pending"}]}
    db.projects["project-1"] = {"id": "project-1", "visual_run_id": "run-2"}
    db.plans = [
        {
            "id": "plan-file",
            "knowledge_project_id": "project-1",
            "item_type": "question",
            "assessment_id": "quiz-1",
            "visual": {"storage_path": "ws/knowledge/project-1/visuals/plan-file/stem.png"},
        },
        {
            "id": "plan-empty",
            "knowledge_project_id": "project-1",
            "item_type": "scenario",
            "assessment_id": "scenario-1",
            "visual": None,
        },
    ]
    db.assessments["quizzes"] = [{"id": "quiz-1", "knowledge_project_id": "project-1", "visual": None}]
    db.assessments["scenarios"] = [
        {"id": "scenario-1", "knowledge_project_id": "project-1", "visual": {"storage_path": "old.png"}},
    ]
    runner = KnowledgeRunner(db=db)

    runner.attach("run-2")

    quiz = db.assessments["quizzes"][0]
    scenario = db.assessments["scenarios"][0]
    assert quiz["visual"]["storage_path"].endswith("stem.png")
    assert scenario["visual"] is None
    assert db.runs["run-2"]["pipeline"][0]["status"] == "completed"
    assert db.projects["project-1"]["status"] == "ready"


class _Projects:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    async def create(self, row: dict[str, Any]) -> dict[str, Any]:
        self.created = {**row, "id": "project-1", "created_at": "2026-10-05T00:00:00Z", "updated_at": "2026-10-05T00:00:00Z"}
        return self.created

    async def update(self, project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        assert self.created is not None
        self.created = {**self.created, **changes, "id": project_id}
        return self.created

    async def insert_plans(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.plans = rows
        return rows


class _Runs:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    async def create(self, row: dict[str, Any]) -> dict[str, Any]:
        self.created = {**row, "id": "run-1"}
        return self.created

    async def update(self, run_id: str, changes: dict[str, Any]) -> None:
        assert self.created is not None
        self.created.update(changes)


class _Batches:
    def __init__(self) -> None:
        self.row: dict[str, Any] | None = None

    async def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        self.row = row
        return row


class _Storage:
    def __init__(self) -> None:
        self.uploaded: str | None = None

    async def upload(self, **kwargs: Any) -> None:
        self.uploaded = kwargs["path"]


def test_notes_file_is_the_batch_attachment_and_the_book_stays_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.knowledge_projects.enqueue_knowledge_run", lambda *args, **kwargs: None)
    projects = _Projects()
    batches = _Batches()
    storage = _Storage()
    service = KnowledgeProjectService(
        projects=projects,
        production_runs=_Runs(),
        batches=batches,
        wiki_entries=object(),
        settings=get_settings(),
    )
    book = {"id": "book-1", "status": "ready", "storage_path": "ws/sources/book-1/original.pdf"}

    asyncio.run(service.create(
        workspace_id="ws-1",
        owner_id="user-1",
        workspace_slug="acme",
        title="Campaign notes",
        source=book,
        raw_notes="",
        filename="notes.md",
        content_type="text/markdown",
        content=b"# Notes\n",
        storage=storage,
    ))

    assert batches.row is not None
    assert batches.row["source_id"] == "book-1"
    assert batches.row["attachments"][0]["storage_path"] == storage.uploaded
    assert storage.uploaded == "acme/knowledge/project-1/notes/notes.md"
    assert "original.pdf" not in storage.uploaded


class _Wiki:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []

    async def list_for_workspace(self, workspace_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        del workspace_id, kwargs
        return []

    async def insert_many(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        saved = [{**row, "id": f"wiki-{index}"} for index, row in enumerate(rows, start=1)]
        self.inserted.extend(saved)
        return saved

    async def update(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": entry_id, **payload}


def test_json_notes_are_stored_on_the_source_and_written_immediately() -> None:
    projects = _Projects()
    batches = _Batches()
    runs = _Runs()
    wiki = _Wiki()
    storage = _Storage()
    service = KnowledgeProjectService(
        projects=projects,
        production_runs=runs,
        batches=batches,
        wiki_entries=wiki,
        settings=get_settings(),
    )
    content = (Path(__file__).parent / "fixtures" / "warfighting-chapter-1.json").read_bytes()

    asyncio.run(service.create(
        workspace_id="ws-1",
        owner_id="user-1",
        workspace_slug="acme",
        title="Chapter 1",
        source={"id": "book-1", "slug": "warfighting", "status": "ready", "source_kind": "document"},
        raw_notes="",
        filename="warfighting-chapter-1.json",
        content_type="application/json",
        content=content,
        storage=storage,
    ))

    assert runs.created is None
    assert batches.row is None
    assert storage.uploaded == "acme/warfighting/knowledge/project-1/warfighting-chapter-1.json"
    assert projects.created is not None
    assert projects.created["status"] == "composing"
    assert projects.plans
    terms = [row for row in wiki.inserted if row["entry_kind"] == "term"]
    lists = [row for row in wiki.inserted if row["entry_kind"] == "list"]
    assert len(lists) == 5
    assert len(terms) >= 23
    friction = next(row for row in terms if row["preferred_label"] == "Friction")
    assert friction["definition"].startswith("The collective force that resists all action")
    assert friction["evidence"] == [{"source_id": "book-1"}]
