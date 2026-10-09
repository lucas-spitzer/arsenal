"""Structure notes, draft study items, and attach uploaded images for a knowledge project."""

from __future__ import annotations

import copy
import logging
from datetime import UTC, datetime
from typing import Any

from app.knowledge.plans import (
    flashcard_plan_rows,
    item_plan_rows,
    plans_by_wiki_id,
    project_wiki_ids,
    study_wiki_ids,
)
from app.knowledge.visuals import cited_wiki_id, storage_path_of
from app.worker.db import WorkerDatabase
from app.worker.pipeline_runner import mark_step
from app.worker.stage_executor import (
    FlashcardGenStageExecutor,
    QuizGenStageExecutor,
    ScenarioGenStageExecutor,
)
from app.worker.wiki_knowledge_executors import (
    StructureWikiNotesStageExecutor,
    TranscribeWikiNotesStageExecutor,
)

logger = logging.getLogger(__name__)

_RUN_COLUMNS = {
    "structure": "structure_run_id",
    "draft": "draft_run_id",
    "attach": "visual_run_id",
}
_ASSESSMENT_TABLES = {
    "flashcard": "flashcards",
    "question": "quizzes",
    "scenario": "scenarios",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class KnowledgeRunner:
    def __init__(
        self,
        db: WorkerDatabase | None = None,
        transcribe: TranscribeWikiNotesStageExecutor | None = None,
        structure: StructureWikiNotesStageExecutor | None = None,
        flashcards: FlashcardGenStageExecutor | None = None,
        questions: QuizGenStageExecutor | None = None,
        scenarios: ScenarioGenStageExecutor | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.transcribe_notes = transcribe or TranscribeWikiNotesStageExecutor(db=self.db)
        self.structure_notes = structure or StructureWikiNotesStageExecutor(db=self.db)
        self.flashcards = flashcards or FlashcardGenStageExecutor(db=self.db)
        self.questions = questions or QuizGenStageExecutor(db=self.db)
        self.scenarios = scenarios or ScenarioGenStageExecutor(db=self.db)

    def structure(self, production_run_id: str) -> dict[str, Any]:
        return self._execute(production_run_id, "structure", self._structure_steps)

    def draft(self, production_run_id: str) -> dict[str, Any]:
        return self._execute(production_run_id, "draft", self._draft_steps)

    def attach(self, production_run_id: str) -> dict[str, Any]:
        return self._execute(production_run_id, "attach", self._attach_steps)

    def _execute(self, production_run_id: str, kind: str, steps) -> dict[str, Any]:
        run = self.db.get_production_run(production_run_id)
        if not run:
            raise RuntimeError(f"Production run not found: {production_run_id}")
        project = self.db.get_knowledge_project_for_run(production_run_id, _RUN_COLUMNS[kind])
        if not project:
            raise RuntimeError(f"No knowledge project is attached to production run {production_run_id}.")

        pipeline = copy.deepcopy(run.get("pipeline") or [])
        self.db.update_production_run(production_run_id, {"status": "running", "error": None})
        try:
            pipeline = steps(project, run, pipeline)
            self.db.update_production_run(
                production_run_id,
                {
                    "status": "completed",
                    "pipeline": pipeline,
                    "error": None,
                    "cost_usd": self.db.sum_stage_run_costs(production_run_id),
                    "completed_at": utc_now_iso(),
                },
            )
            return {"production_run_id": production_run_id, "status": "completed"}
        except Exception as exc:
            logger.exception("Knowledge %s run %s failed", kind, production_run_id)
            self.db.update_production_run(
                production_run_id,
                {
                    "status": "failed",
                    "pipeline": pipeline,
                    "error": str(exc),
                    "cost_usd": self.db.sum_stage_run_costs(production_run_id),
                    "completed_at": utc_now_iso(),
                },
            )
            restored = {"structure": "failed", "draft": "composing", "attach": "ready"}[kind]
            self.db.update_knowledge_project(
                str(project["id"]),
                {"status": restored, "error": str(exc)[:2000]},
            )
            raise

    def _structure_steps(
        self,
        project: dict[str, Any],
        run: dict[str, Any],
        pipeline: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        source_id = str(project["source_id"])
        workspace_id = str(project["workspace_id"])
        run_id = str(run["id"])
        pipeline = self._run_named_step(
            pipeline,
            "transcribe-wiki-notes",
            lambda: self.transcribe_notes.run(
                production_run_id=run_id,
                workspace_id=workspace_id,
                source_id=source_id,
            ),
        )
        self.db.update_production_run(run_id, {"pipeline": pipeline})
        pipeline = self._run_named_step(
            pipeline,
            "structure-wiki-notes",
            lambda: self.structure_notes.run(
                production_run_id=run_id,
                workspace_id=workspace_id,
                source_id=source_id,
            ),
        )
        batch = self.db.get_wiki_ingest_batch_for_run(run_id, source_id=source_id)
        entry_ids = [str(entry_id) for entry_id in (batch or {}).get("committed_entry_ids") or []]
        entries = self.db.get_wiki_entries(entry_ids)
        if not entries:
            raise RuntimeError("Structuring finished without any wiki entries.")
        self.db.insert_knowledge_item_plans(
            flashcard_plan_rows(
                project_id=str(project["id"]),
                workspace_id=workspace_id,
                entries=entries,
            ),
        )
        self.db.update_knowledge_project(str(project["id"]), {"status": "composing", "error": None})
        return pipeline

    def _draft_steps(
        self,
        project: dict[str, Any],
        run: dict[str, Any],
        pipeline: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        project_id = str(project["id"])
        workspace_id = str(project["workspace_id"])
        source = self._source(str(project["source_id"]))
        plans = self.db.list_knowledge_item_plans(project_id)
        all_ids = project_wiki_ids(plans)
        entries = self.db.get_wiki_entries(list(all_ids)) if all_ids else []
        # Checked rows, with a checked list pulling in the terms it names.
        # Questions and scenarios with nothing checked still use every entry.
        study_ids = study_wiki_ids(plans, entries)
        flashcard_ids = study_ids
        drafted_ids = study_ids or all_ids
        self.db.delete_assessments_for_project(project_id)
        self.db.delete_knowledge_item_plans(project_id, ["question", "scenario"])
        self.db.clear_plan_assessments(project_id, "flashcard")

        if flashcard_ids and _has_step(pipeline, "generate-flashcards"):
            pipeline = self._run_named_step(
                pipeline,
                "generate-flashcards",
                lambda: self.flashcards.run_for_source(
                    production_run_id=str(run["id"]),
                    workspace_id=workspace_id,
                    source=source,
                    wiki_ids=flashcard_ids,
                    knowledge_project_id=project_id,
                    skip_importance_filter=True,
                ),
            )
            self.db.update_production_run(str(run["id"]), {"pipeline": pipeline})

        if project.get("draft_questions") and drafted_ids and _has_step(pipeline, "generate-questions"):
            pipeline = self._run_named_step(
                pipeline,
                "generate-questions",
                lambda: self.questions.run_for_source(
                    production_run_id=str(run["id"]),
                    workspace_id=workspace_id,
                    source=source,
                    wiki_ids=drafted_ids,
                    knowledge_project_id=project_id,
                ),
            )
            self.db.update_production_run(str(run["id"]), {"pipeline": pipeline})

        if project.get("draft_scenarios") and drafted_ids and _has_step(pipeline, "generate-scenarios"):
            pipeline = self._run_named_step(
                pipeline,
                "generate-scenarios",
                lambda: self.scenarios.run_for_source(
                    production_run_id=str(run["id"]),
                    workspace_id=workspace_id,
                    source=source,
                    wiki_ids=drafted_ids,
                    knowledge_project_id=project_id,
                    skip_importance_filter=True,
                ),
            )
            self.db.update_production_run(str(run["id"]), {"pipeline": pipeline})

        fresh_plans = self.db.list_knowledge_item_plans(project_id)
        pipeline = self._link_flashcards(project_id, fresh_plans, pipeline)
        self._create_followup_plans(project_id, workspace_id)
        self.db.update_knowledge_project(project_id, {"status": "ready", "error": None})
        return pipeline

    def _attach_steps(
        self,
        project: dict[str, Any],
        run: dict[str, Any],
        pipeline: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        project_id = str(project["id"])
        plans = self.db.list_knowledge_item_plans(project_id)
        pipeline = self._copy_visuals(project_id, plans, pipeline)
        self.db.update_knowledge_project(project_id, {"status": "ready", "error": None})
        return pipeline

    def _link_flashcards(
        self,
        project_id: str,
        plans: list[dict[str, Any]],
        pipeline: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = self.db.list_assessments_for_project("flashcards", project_id)
        by_wiki = plans_by_wiki_id(plans, "flashcard")
        attached = 0
        for row in rows:
            plan = by_wiki.get(cited_wiki_id(row.get("citations")) or "")
            if not plan:
                continue
            self.db.update_knowledge_item_plan(str(plan["id"]), {"assessment_id": str(row["id"])})
            visual = plan.get("visual") if isinstance(plan.get("visual"), dict) else None
            if not storage_path_of(visual):
                continue
            self.db.update_assessment("flashcards", str(row["id"]), {"visual": visual})
            attached += 1
        detail = f"{attached} image(s)" if attached else "No images to attach"
        return mark_step(pipeline, "attach-visuals", status="completed", detail=detail)

    def _copy_visuals(
        self,
        project_id: str,
        plans: list[dict[str, Any]],
        pipeline: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        attached = 0
        for plan in plans:
            assessment_id = plan.get("assessment_id")
            if not assessment_id:
                continue
            table = _ASSESSMENT_TABLES.get(str(plan.get("item_type") or ""))
            if not table:
                continue
            visual = plan.get("visual") if isinstance(plan.get("visual"), dict) else None
            if not storage_path_of(visual):
                self.db.update_assessment(table, str(assessment_id), {"visual": None})
                continue
            self.db.update_assessment(table, str(assessment_id), {"visual": visual})
            attached += 1
        detail = f"{attached} image(s)" if attached else "No images to attach"
        return mark_step(pipeline, "attach-visuals", status="completed", detail=detail)

    def _create_followup_plans(self, project_id: str, workspace_id: str) -> None:
        for item_type, table in (("question", "quizzes"), ("scenario", "scenarios")):
            rows = self.db.list_assessments_for_project(table, project_id)
            planned = item_plan_rows(
                project_id=project_id,
                workspace_id=workspace_id,
                rows=rows,
                item_type=item_type,
            )
            if planned:
                self.db.insert_knowledge_item_plans(planned)

    def _source(self, source_id: str) -> dict[str, Any]:
        sources = self.db.get_sources([source_id])
        if not sources:
            raise RuntimeError(f"Source {source_id} no longer exists.")
        return sources[0]

    def _run_named_step(self, pipeline: list[dict[str, Any]], step_name: str, action) -> list[dict[str, Any]]:
        pipeline[:] = mark_step(pipeline, step_name, status="running")
        try:
            stage_run_id = action()
        except Exception:
            pipeline[:] = mark_step(pipeline, step_name, status="failed")
            raise
        pipeline[:] = mark_step(pipeline, step_name, status="completed", stage_run_id=stage_run_id)
        return pipeline


def _has_step(pipeline: list[dict[str, Any]], step_name: str) -> bool:
    return any(step.get("step") == step_name for step in pipeline)
