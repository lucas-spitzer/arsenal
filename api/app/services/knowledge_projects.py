"""Create a knowledge project and queue its structure, draft, and image runs."""

from __future__ import annotations

import logging
import random
import zlib
from typing import Any

from app.artifact_paths import knowledge_notes_path, knowledge_visual_path, source_knowledge_notes_path
from app.config import Settings
from app.intellex.wiki_candidates import WikiCandidate, promote_candidates
from app.knowledge.answer_pool import (
    BLOOM_LEVELS,
    TRUE_FALSE,
    TRUE_FALSE_OPTIONS,
    AnswerPool,
    AnswerPoolError,
    Draw,
    draw,
    validate_pool,
)
from app.knowledge.cards import (
    LAYOUTS,
    PLACEMENT_FOR_LAYOUT,
    QUESTION_FORMATS,
    SCENARIO_FORMATS,
    entries_in_category,
    entry_category,
    flashcard_sides,
    layout_needs_image,
)
from app.knowledge.plans import enabled_flashcard_wiki_ids, flashcard_plan_rows
from app.knowledge.structured_notes import StructuredNotes, StructuredNotesError, require_structured_notes
from app.knowledge.visuals import (
    VisualError,
    normalize_visual,
    storage_path_of,
    validate_image_upload,
    visual_for_response,
)
from app.qngen.canonical_context import ConceptCard
from app.qngen.skills.shared.item_mapping import normalize_question_type
from app.qngen.stages.quiz_gen import QuizGenStage
from app.qngen.stages.scenario_gen import ScenarioGenStage
from app.pipeline import (
    KNOWLEDGE_DRAFT_TARGET,
    KNOWLEDGE_STRUCTURE_TARGET,
    KNOWLEDGE_VISUAL_TARGET,
    build_knowledge_draft_pipeline,
    build_knowledge_structure_pipeline,
    build_knowledge_visual_pipeline,
)
from app.repositories.knowledge_projects import KnowledgeProjectRepository
from app.repositories.production_runs import ProductionRunRepository
from app.repositories.wiki_entries import WikiEntryRepository
from app.repositories.wiki_ingest_batches import WikiIngestBatchRepository
from app.services.queue import enqueue_knowledge_run
from app.services.supabase_storage import SupabaseStorageClient
from app.services.source_upload import sanitize_upload_filename
from app.services.wiki_transcription import validate_note_attachment

logger = logging.getLogger(__name__)

# Bloom levels rotated across a "spread" variant batch.
SPREAD_BLOOM = ("remember", "understand", "apply")
TABLE_FOR_KIND = {"question": "quizzes", "scenario": "scenarios"}


class KnowledgeProjectError(ValueError):
    """The project cannot be created or changed in its current state."""


class KnowledgeProjectService:
    def __init__(
        self,
        *,
        projects: KnowledgeProjectRepository,
        production_runs: ProductionRunRepository,
        batches: WikiIngestBatchRepository,
        wiki_entries: WikiEntryRepository,
        settings: Settings,
    ) -> None:
        self.projects = projects
        self.production_runs = production_runs
        self.batches = batches
        self.wiki_entries = wiki_entries
        self.settings = settings

    async def create(
        self,
        *,
        workspace_id: str,
        owner_id: str,
        workspace_slug: str,
        title: str,
        source: dict[str, Any],
        raw_notes: str,
        filename: str | None,
        content_type: str | None,
        content: bytes | None,
        storage: SupabaseStorageClient,
    ) -> dict[str, Any]:
        cleaned_title = " ".join(title.split())
        if not cleaned_title:
            raise KnowledgeProjectError("Give the project a title.")
        notes = raw_notes.strip()
        has_file = bool(content)
        structured = _structured_upload(filename, content_type, content) if has_file else None
        if has_file and notes:
            raise KnowledgeProjectError("Upload a notes file or paste notes, not both.")
        if not has_file and not notes:
            raise KnowledgeProjectError("Upload a notes file or paste notes.")
        if notes and len(notes) > self.settings.wiki_authoring.max_notes_chars:
            raise KnowledgeProjectError("Notes are too long.")
        if source.get("source_kind", "document") != "document":
            raise KnowledgeProjectError("The book must be a document source.")
        if source.get("status") != "ready":
            raise KnowledgeProjectError("Choose a source that has finished ingest.")

        attachment = None
        if has_file and structured is None:
            assert content is not None
            attachment = validate_note_attachment(
                order=0,
                filename=filename,
                content_type=content_type,
                content=content,
                max_bytes=self.settings.wiki_authoring.max_attachment_bytes,
            )

        project = await self.projects.create(
            {
                "workspace_id": workspace_id,
                "owner_id": owner_id,
                "source_id": source["id"],
                "title": cleaned_title,
                "status": "composing" if structured is not None else "structuring",
                "raw_notes": structured[0] if structured is not None else notes,
                "notes_filename": structured[1] if structured is not None else (attachment.filename if attachment else None),
                "notes_mime_type": (
                    "application/json" if structured is not None else (attachment.mime_type if attachment else None)
                ),
                "notes_byte_size": len(content) if content is not None and (structured is not None or attachment) else None,
            },
        )
        project_id = str(project["id"])
        if structured is not None:
            return await self._commit_structured_project(
                project,
                source=source,
                workspace_slug=workspace_slug,
                filename=structured[1],
                text=structured[0],
                content=content or b"",
                storage=storage,
            )
        run = await self.production_runs.create(
            {
                "workspace_id": workspace_id,
                "owner_id": owner_id,
                "label": cleaned_title,
                "source_ids": [source["id"]],
                "target_artifacts": [KNOWLEDGE_STRUCTURE_TARGET],
                "pipeline": build_knowledge_structure_pipeline(),
                "status": "queued",
            },
        )
        run_id = str(run["id"])
        notes_path = None
        batch_attachments: list[dict[str, Any]] = []
        if attachment and content is not None:
            notes_path = knowledge_notes_path(workspace_slug, project_id, attachment.filename)
            batch_attachments.append(
                {
                    "order": 0,
                    "filename": attachment.filename,
                    "mime_type": attachment.mime_type,
                    "storage_path": notes_path,
                    "byte_size": len(content),
                },
            )

        try:
            if notes_path and content is not None and attachment is not None:
                await storage.upload(
                    bucket=self.settings.sources_bucket,
                    path=notes_path,
                    content=content,
                    content_type=attachment.mime_type,
                    upsert=True,
                )
            await self.batches.insert(
                {
                    "workspace_id": workspace_id,
                    "source_id": source["id"],
                    "production_run_id": run_id,
                    "title": cleaned_title,
                    "raw_notes": notes,
                    "status": "transcribed" if notes else "transcribing",
                    "entries": [],
                    "unparsed_fragments": [],
                    "attachments": batch_attachments,
                },
            )
            updated = await self.projects.update(
                project_id,
                {
                    "structure_run_id": run_id,
                    "notes_storage_path": notes_path,
                    "error": None,
                },
            )
            enqueue_knowledge_run(self.settings, run_id, "structure")
        except Exception as exc:
            logger.exception("Failed to start knowledge structure for %s", project_id)
            await self.production_runs.update(run_id, {"status": "failed", "error": str(exc)})
            await self.projects.update(
                project_id,
                {"status": "failed", "structure_run_id": run_id, "error": "Could not queue structuring."},
            )
            raise KnowledgeProjectError("Structuring could not be queued. Is Redis running?") from exc
        return updated or project

    async def _commit_structured_project(
        self,
        project: dict[str, Any],
        *,
        source: dict[str, Any],
        workspace_slug: str,
        filename: str,
        text: str,
        content: bytes,
        storage: SupabaseStorageClient,
    ) -> dict[str, Any]:
        source_slug = str(source.get("slug") or "").strip()
        project_id = str(project["id"])
        if not source_slug:
            await self.projects.update(project_id, {"status": "failed", "error": "Source has no folder."})
            raise KnowledgeProjectError("This source has no folder yet.")
        path = source_knowledge_notes_path(workspace_slug, source_slug, project_id, filename)
        try:
            await storage.upload(
                bucket=self.settings.sources_bucket,
                path=path,
                content=content,
                content_type="application/json",
                upsert=True,
            )
            notes = require_structured_notes(text, filename=filename)
            saved = await self._write_wiki_entries(
                workspace_id=str(project["workspace_id"]),
                source_id=str(source["id"]),
                notes=notes,
            )
            await self.projects.insert_plans(
                flashcard_plan_rows(
                    project_id=project_id,
                    workspace_id=str(project["workspace_id"]),
                    entries=saved,
                ),
            )
            updated = await self.projects.update(
                project_id,
                {"notes_storage_path": path, "status": "composing", "error": None},
            )
            return updated or project
        except KnowledgeProjectError:
            raise
        except Exception as exc:
            logger.exception("Failed to import structured notes for %s", project_id)
            await self.projects.update(project_id, {"status": "failed", "error": str(exc)[:2000]})
            raise KnowledgeProjectError("Could not import the JSON notes.") from exc

    async def _write_wiki_entries(
        self,
        *,
        workspace_id: str,
        source_id: str,
        notes: StructuredNotes,
    ) -> list[dict[str, Any]]:
        existing = await self.wiki_entries.list_for_workspace(workspace_id, status="canonical", limit=1000)
        candidates = _candidates(notes, source_id)
        inserts, updates, conflicted = promote_candidates(
            workspace_id=workspace_id,
            candidates=candidates,
            existing_entries=existing,
        )
        saved: list[dict[str, Any]] = []
        if inserts:
            saved.extend(await self.wiki_entries.insert_many(inserts))
        for row in updates:
            entry_id = str(row.pop("id"))
            saved.append(await self.wiki_entries.update(entry_id, row))
        existing_by_key = {
            (str(entry.get("preferred_label") or "").casefold(), str(entry.get("entry_kind") or "term")): entry
            for entry in existing
        }
        for index in conflicted:
            candidate = candidates[index]
            match = existing_by_key.get((candidate.label.casefold(), candidate.entry_kind))
            if match:
                saved.append(match)
        if not saved:
            raise KnowledgeProjectError("The JSON matched wiki entries that already disagree, so nothing was written.")
        return saved

    async def update_switches(
        self,
        project: dict[str, Any],
        *,
        draft_questions: bool | None,
        draft_scenarios: bool | None,
        batch_instructions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self._require_status(project, "composing")
        changes: dict[str, Any] = {}
        if draft_questions is not None:
            changes["draft_questions"] = draft_questions
        if draft_scenarios is not None:
            changes["draft_scenarios"] = draft_scenarios
        if batch_instructions is not None:
            current = dict(project.get("batch_instructions") or {})
            for category, text in batch_instructions.items():
                cleaned = text.strip()
                if cleaned:
                    current[category] = cleaned
                else:
                    current.pop(category, None)
            changes["batch_instructions"] = current
        if not changes:
            return project
        updated = await self.projects.update(str(project["id"]), changes)
        return updated or project

    async def set_plan_instructions(self, project: dict[str, Any], plan: dict[str, Any], text: str) -> dict[str, Any]:
        self._require_status(project, "composing")
        updated = await self.projects.update_plan(str(plan["id"]), {"instructions": text.strip()})
        return updated or plan

    async def set_plan_draft(
        self,
        project: dict[str, Any],
        plan: dict[str, Any],
        draft: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self._require_status(project, "composing")
        updated = await self.projects.update_plan(str(plan["id"]), {"draft": draft})
        return updated or plan

    async def set_plan_enabled(self, project: dict[str, Any], plan: dict[str, Any], enabled: bool) -> dict[str, Any]:
        self._require_status(project, "composing")
        if plan.get("item_type") != "flashcard":
            raise KnowledgeProjectError("Only flashcard rows can be toggled before drafting.")
        updated = await self.projects.update_plan(str(plan["id"]), {"enabled": enabled})
        return updated or plan

    async def set_plan_layout(self, project: dict[str, Any], plan: dict[str, Any], layout: str) -> dict[str, Any]:
        self._require_status(project, "composing")
        if plan.get("item_type") != "flashcard":
            raise KnowledgeProjectError("Only flashcard rows have a layout.")
        if layout not in LAYOUTS:
            raise KnowledgeProjectError("Choose a flashcard layout.")
        updated = await self.projects.update_plan(str(plan["id"]), {"layout": layout})
        return updated or plan

    async def make_flashcards(self, project: dict[str, Any]) -> dict[str, Any]:
        self._require_status(project, "composing")
        project_id = str(project["id"])
        plans = await self.projects.list_plans(project_id)
        selected = [
            plan
            for plan in plans
            if plan.get("item_type") == "flashcard" and plan.get("enabled") and plan.get("wiki_entry_id")
        ]
        if not selected:
            raise KnowledgeProjectError("Check at least one entry.")
        entries = await self.wiki_entries.get_many([str(plan["wiki_entry_id"]) for plan in selected])
        by_id = {str(entry["id"]): entry for entry in entries}
        rows: list[dict[str, Any]] = []
        used_plans: list[dict[str, Any]] = []
        for plan in selected:
            entry = by_id.get(str(plan["wiki_entry_id"]))
            if not entry:
                continue
            layout = str(plan.get("layout") or "label_description")
            visual = plan.get("visual") if isinstance(plan.get("visual"), dict) else None
            if layout_needs_image(layout) and not storage_path_of(visual):
                raise KnowledgeProjectError(f"{entry.get('preferred_label')} needs an image for this layout.")
            rows.append(_flashcard_row(project, plan, entry))
            used_plans.append(plan)
        if not rows:
            raise KnowledgeProjectError("Check at least one entry.")
        existing = await self.projects.list_assessments("flashcards", project_id)
        await self.projects.delete_rows("flashcards", [str(row["id"]) for row in existing])
        for plan in plans:
            if plan.get("item_type") == "flashcard" and plan.get("assessment_id"):
                await self.projects.update_plan(str(plan["id"]), {"assessment_id": None})
        saved = await self.projects.insert_rows("flashcards", rows)
        for plan, card in zip(used_plans, saved, strict=True):
            await self.projects.update_plan(str(plan["id"]), {"assessment_id": card["id"]})
        return project

    async def save_flashcard(
        self,
        project: dict[str, Any],
        plan: dict[str, Any],
        *,
        front: str,
        back: str,
    ) -> dict[str, Any]:
        """Write one entry's card with author-edited faces.

        The text is also kept on the plan so a later "Make all flashcards"
        keeps the edit instead of regenerating from the wiki.
        """
        self._require_status(project, "composing")
        if plan.get("item_type") != "flashcard" or not plan.get("wiki_entry_id"):
            raise KnowledgeProjectError("Only entry rows have a flashcard.")
        front_text = front.strip()
        back_text = back.strip()
        if not front_text or not back_text:
            raise KnowledgeProjectError("Both card faces need text.")
        entries = await self.wiki_entries.get_many([str(plan["wiki_entry_id"])])
        if not entries:
            raise KnowledgeProjectError("The wiki entry for this card is gone.")
        layout = str(plan.get("layout") or "label_description")
        visual = plan.get("visual") if isinstance(plan.get("visual"), dict) else None
        if layout_needs_image(layout) and not storage_path_of(visual):
            raise KnowledgeProjectError("This layout needs an image.")
        card_override = {"front": front_text, "back": back_text}
        plan_with_card = {**plan, "draft": {**(plan.get("draft") or {}), "card": card_override}}
        row = _flashcard_row(project, plan_with_card, entries[0])
        if plan.get("assessment_id"):
            await self.projects.delete_rows("flashcards", [str(plan["assessment_id"])])
        saved = await self.projects.insert_rows("flashcards", [row])
        updated = await self.projects.update_plan(
            str(plan["id"]),
            {"assessment_id": saved[0]["id"], "enabled": True, "draft": plan_with_card["draft"]},
        )
        return updated or plan

    async def generate_batch(
        self,
        project: dict[str, Any],
        *,
        kind: str,
        category: str,
        item_format: str,
        instructions: str,
        per_entry: int = 1,
        bloom_level: str = "",
        mode: str = "append",
    ) -> dict[str, Any]:
        """Generate ``per_entry`` items for every entry in a category.

        ``replace`` drops that category's existing items first; ``append``
        keeps them and asks the model not to repeat their stems.
        """
        self._require_status(project, "composing")
        _check_format(kind, item_format)
        _check_bloom(bloom_level)
        per_entry = max(1, min(3, per_entry))
        project_id = str(project["id"])
        entries = await self._planned_entries(project_id)
        batch = entries_in_category(entries, category)
        if not batch:
            raise KnowledgeProjectError(f"No entries in {category}.")
        table = TABLE_FOR_KIND[kind]
        existing = await self.projects.list_assessments(table, project_id)
        batch_ids = {str(entry["id"]) for entry in batch}
        avoid = [] if mode == "replace" else _stems(kind, [row for row in existing if _cited_wiki_ids(row) & batch_ids])
        generated = self._run_stage(
            project,
            kind=kind,
            concepts=[_concept(entry) for entry in batch],
            item_format=item_format,
            bloom_level=bloom_level,
            items_per_concept=per_entry,
            instructions=_join_notes(_category_note(project, category), instructions),
            avoid_stems=avoid,
            context_concepts=[],
        )
        if not generated:
            raise KnowledgeProjectError(f"No {kind}s came back for {category}.")
        rows = _assessment_rows(project, kind=kind, category=category, item_format=item_format, generated=generated)
        if mode == "replace":
            await self._delete_items(project, table=table, item_type=kind, batch_ids=batch_ids)
        await self._insert_items(project, table=table, item_type=kind, rows=rows)
        return project

    async def generate_variants(
        self,
        project: dict[str, Any],
        *,
        wiki_entry_id: str,
        kind: str,
        item_format: str,
        count: int = 1,
        mix: str = "same",
        bloom_level: str = "",
        instructions: str = "",
    ) -> dict[str, Any]:
        """Add ``count`` new items for one entry.

        ``spread`` rotates the format and Bloom level across the count so the
        variants differ in kind, not only wording. Sibling entries from the
        same category are offered as distractor material.
        """
        self._require_status(project, "composing")
        _check_format(kind, item_format)
        _check_bloom(bloom_level)
        count = max(1, min(5, count))
        project_id = str(project["id"])
        entries = await self._planned_entries(project_id)
        entry = next((row for row in entries if str(row["id"]) == wiki_entry_id), None)
        if not entry:
            raise KnowledgeProjectError("That entry is not part of this project.")
        category = entry_category(entry)
        siblings = [row for row in entries_in_category(entries, category) if str(row["id"]) != wiki_entry_id]
        plans = await self.projects.list_plans(project_id)
        own_plan = next(
            (
                plan
                for plan in plans
                if plan.get("item_type") == "flashcard" and str(plan.get("wiki_entry_id") or "") == wiki_entry_id
            ),
            None,
        )
        note = _join_notes(
            _category_note(project, category),
            str((own_plan or {}).get("instructions") or ""),
            instructions,
        )
        table = TABLE_FOR_KIND[kind]
        existing = await self.projects.list_assessments(table, project_id)
        avoid = _stems(kind, [row for row in existing if wiki_entry_id in _cited_wiki_ids(row)])
        concept = _concept(entry)
        context = [_concept(row) for row in siblings[:8]]

        rounds: list[tuple[str, str, int]]
        if mix == "spread" and kind == "question":
            formats = QUESTION_FORMATS
            rounds = [(formats[i % len(formats)], SPREAD_BLOOM[i % len(SPREAD_BLOOM)], 1) for i in range(count)]
        else:
            rounds = [(item_format, bloom_level, count)]

        rows: list[dict[str, Any]] = []
        for round_format, round_bloom, round_count in rounds:
            generated = self._run_stage(
                project,
                kind=kind,
                concepts=[concept],
                item_format=round_format,
                bloom_level=round_bloom,
                items_per_concept=round_count,
                instructions=note,
                avoid_stems=avoid,
                context_concepts=context,
            )
            avoid = [*avoid, *_stems(kind, generated)]
            rows.extend(
                _assessment_rows(project, kind=kind, category=category, item_format=round_format, generated=generated),
            )
        if not rows:
            raise KnowledgeProjectError(f"No {kind}s came back for {entry.get('preferred_label')}.")
        await self._insert_items(project, table=table, item_type=kind, rows=rows)
        return project

    async def save_item(
        self,
        project: dict[str, Any],
        plan: dict[str, Any],
        *,
        kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace the saved question or scenario behind a plan with edited fields."""
        self._require_status(project, "composing")
        if plan.get("item_type") != kind or not plan.get("assessment_id"):
            raise KnowledgeProjectError(f"This row is not a saved {kind}.")
        item_format = str(payload.get("format") or "")
        _check_format(kind, item_format)
        bloom = payload.get("bloom_level") or None
        if bloom is not None:
            _check_bloom(str(bloom))
        difficulty = str(payload.get("difficulty") or "medium")
        if difficulty not in {"easy", "medium", "hard"}:
            raise KnowledgeProjectError("Choose a difficulty.")
        if kind == "question":
            changes = _question_changes(payload, item_format=item_format)
        else:
            changes = _scenario_changes(payload, item_format=item_format)
        changes["bloom_level"] = bloom
        changes["difficulty"] = difficulty
        await self.projects.update_row(TABLE_FOR_KIND[kind], str(plan["assessment_id"]), changes)
        updated = await self.projects.update_plan(str(plan["id"]), {"draft": None})
        return updated or plan

    async def duplicate_item(self, project: dict[str, Any], plan: dict[str, Any]) -> None:
        """Copy a saved question or scenario into a new variant."""
        self._require_status(project, "composing")
        kind = str(plan.get("item_type") or "")
        if kind not in TABLE_FOR_KIND or not plan.get("assessment_id"):
            raise KnowledgeProjectError("Only a saved question or scenario can be duplicated.")
        table = TABLE_FOR_KIND[kind]
        rows = await self.projects.list_assessments(table, str(project["id"]))
        source = next((row for row in rows if str(row["id"]) == str(plan["assessment_id"])), None)
        if source is None:
            raise KnowledgeProjectError("That item is gone.")
        copy = {key: value for key, value in source.items() if key not in {"id", "created_at"}}
        await self._insert_items(project, table=table, item_type=kind, rows=[copy])

    async def delete_item(self, project: dict[str, Any], plan: dict[str, Any]) -> None:
        self._require_status(project, "composing")
        kind = str(plan.get("item_type") or "")
        if kind not in TABLE_FOR_KIND:
            raise KnowledgeProjectError("Only questions and scenarios can be removed here.")
        if plan.get("assessment_id"):
            await self.projects.delete_rows(TABLE_FOR_KIND[kind], [str(plan["assessment_id"])])
        await self.projects.delete_rows("knowledge_item_plans", [str(plan["id"])])

    async def _planned_entries(self, project_id: str) -> list[dict[str, Any]]:
        plans = await self.projects.list_plans(project_id)
        wiki_ids = [
            str(plan["wiki_entry_id"])
            for plan in plans
            if plan.get("item_type") == "flashcard" and plan.get("wiki_entry_id")
        ]
        return await self.wiki_entries.get_many(wiki_ids) if wiki_ids else []

    def _run_stage(
        self,
        project: dict[str, Any],
        *,
        kind: str,
        concepts: list[ConceptCard],
        item_format: str,
        bloom_level: str,
        items_per_concept: int,
        instructions: str,
        avoid_stems: list[str],
        context_concepts: list[ConceptCard],
    ) -> list[dict[str, Any]]:
        shared = {
            "source_metadata": {"title": str(project.get("title") or "")},
            "concepts": concepts,
            "concept_batches": [concepts],
            "learning_objectives": [],
            "chapters": [],
            "instructions": instructions,
            "required_subtype": item_format,
            "bloom_level": bloom_level,
            "items_per_concept": items_per_concept,
            "avoid_stems": avoid_stems,
            "context_concepts": context_concepts,
        }
        if kind == "question":
            output, _execution = QuizGenStage().run(**shared)
            return [question.model_dump() for question in output.questions]
        output, _execution = ScenarioGenStage().run(skip_importance_filter=True, **shared)
        return [scenario.model_dump() for scenario in output.scenarios]

    async def _delete_items(
        self,
        project: dict[str, Any],
        *,
        table: str,
        item_type: str,
        batch_ids: set[str],
    ) -> None:
        project_id = str(project["id"])
        existing = await self.projects.list_assessments(table, project_id)
        stale_ids = [str(row["id"]) for row in existing if _cited_wiki_ids(row) & batch_ids]
        await self.projects.delete_rows(table, stale_ids)
        plans = await self.projects.list_plans(project_id)
        stale_plans = [
            str(plan["id"])
            for plan in plans
            if plan.get("item_type") == item_type and str(plan.get("assessment_id") or "") in set(stale_ids)
        ]
        await self.projects.delete_rows("knowledge_item_plans", stale_plans)

    async def _insert_items(
        self,
        project: dict[str, Any],
        *,
        table: str,
        item_type: str,
        rows: list[dict[str, Any]],
    ) -> None:
        project_id = str(project["id"])
        saved = await self.projects.insert_rows(table, rows)
        plan_rows = []
        for row in saved:
            cited = _cited_wiki_ids(row)
            plan_rows.append(
                {
                    "knowledge_project_id": project_id,
                    "workspace_id": project["workspace_id"],
                    "wiki_entry_id": next(iter(cited), None),
                    "item_type": item_type,
                    "enabled": True,
                    "assessment_id": row["id"],
                    "layout": "label_description",
                },
            )
        await self.projects.insert_plans(plan_rows)

    async def save_visual(
        self,
        *,
        project: dict[str, Any],
        plan: dict[str, Any],
        workspace_slug: str,
        filename: str | None,
        content_type: str | None,
        content: bytes,
        kind: str,
        placement: str | None,
        alt: str | None,
        storage: SupabaseStorageClient,
    ) -> dict[str, Any]:
        self._require_visual_edit(project, plan)
        safe_name, mime_type = validate_image_upload(
            filename=filename,
            content_type=content_type,
            content=content,
            max_bytes=self.settings.study_material.max_file_bytes,
        )
        path = knowledge_visual_path(workspace_slug, str(project["id"]), str(plan["id"]), safe_name)
        visual = normalize_visual(
            item_type=str(plan["item_type"]),
            kind=kind,
            placement=placement,
            alt=alt,
            storage_path=path,
            mime_type=mime_type,
            filename=safe_name,
            byte_size=len(content),
        )
        await storage.upload(
            bucket=self.settings.sources_bucket,
            path=path,
            content=content,
            content_type=mime_type,
            upsert=True,
        )
        previous = storage_path_of(plan.get("visual") if isinstance(plan.get("visual"), dict) else None)
        updated = await self.projects.update_plan(str(plan["id"]), {"visual": visual})
        if previous and previous != path:
            try:
                await storage.delete(bucket=self.settings.sources_bucket, path=previous)
            except Exception:
                logger.exception("Could not delete replaced visual %s", previous)
        return updated or plan

    async def clear_visual(
        self,
        *,
        project: dict[str, Any],
        plan: dict[str, Any],
        storage: SupabaseStorageClient,
    ) -> dict[str, Any]:
        self._require_visual_edit(project, plan)
        previous = storage_path_of(plan.get("visual") if isinstance(plan.get("visual"), dict) else None)
        updated = await self.projects.update_plan(str(plan["id"]), {"visual": None})
        if previous:
            try:
                await storage.delete(bucket=self.settings.sources_bucket, path=previous)
            except Exception:
                logger.exception("Could not delete visual %s", previous)
        return updated or plan

    async def start_draft(self, project: dict[str, Any]) -> dict[str, Any]:
        self._require_status(project, "composing")
        plans = await self.projects.list_plans(str(project["id"]))
        flashcards = bool(enabled_flashcard_wiki_ids(plans))
        questions = bool(project.get("draft_questions"))
        scenarios = bool(project.get("draft_scenarios"))
        if not flashcards and not questions and not scenarios:
            raise KnowledgeProjectError("Turn on at least one flashcard, or draft questions or scenarios.")
        return await self._enqueue(
            project,
            run_column="draft_run_id",
            target=KNOWLEDGE_DRAFT_TARGET,
            pipeline=build_knowledge_draft_pipeline(
                flashcards=flashcards,
                questions=questions,
                scenarios=scenarios,
            ),
            job="draft",
            failure="Could not queue drafting.",
        )

    async def start_attach(self, project: dict[str, Any]) -> dict[str, Any]:
        self._require_status(project, "ready")
        return await self._enqueue(
            project,
            run_column="visual_run_id",
            target=KNOWLEDGE_VISUAL_TARGET,
            pipeline=build_knowledge_visual_pipeline(),
            job="attach",
            failure="Could not queue the image update.",
        )

    async def detail(
        self,
        project: dict[str, Any],
        *,
        storage: SupabaseStorageClient,
    ) -> dict[str, Any]:
        plans = await self.projects.list_plans(str(project["id"]))
        wiki_ids = [str(plan["wiki_entry_id"]) for plan in plans if plan.get("wiki_entry_id")]
        entries = await self.wiki_entries.get_many(wiki_ids) if wiki_ids else []
        by_id = {str(entry["id"]): entry for entry in entries}
        signed = await self._sign_paths(self._visual_paths(plans), storage)
        run_id = self._active_run_id(project)
        run = await self.production_runs.get(run_id) if run_id else None
        pipeline = list((run or {}).get("pipeline") or [])

        entry_views: list[dict[str, Any]] = []
        item_views: list[dict[str, Any]] = []
        assessments = await self._assessments_by_id(str(project["id"]))
        questions_by_entry: dict[str, list[dict[str, Any]]] = {}
        scenarios_by_entry: dict[str, list[dict[str, Any]]] = {}
        for plan in plans:
            item_type = str(plan.get("item_type") or "")
            row = assessments.get(str(plan.get("assessment_id") or ""))
            entry_id = str(plan.get("wiki_entry_id") or "")
            if not row or not entry_id:
                continue
            if item_type == "question":
                questions_by_entry.setdefault(entry_id, []).append(_question_view(plan, row))
            elif item_type == "scenario":
                scenarios_by_entry.setdefault(entry_id, []).append(_scenario_view(plan, row))
        for plan in plans:
            visual = visual_for_response(
                plan.get("visual") if isinstance(plan.get("visual"), dict) else None,
                signed.get(storage_path_of(plan.get("visual")) or ""),
            )
            item_type = str(plan.get("item_type") or "")
            if item_type == "flashcard" and plan.get("wiki_entry_id"):
                entry = by_id.get(str(plan["wiki_entry_id"]))
                if not entry:
                    continue
                card = assessments.get(str(plan.get("assessment_id") or ""))
                entry_views.append(
                    {
                        "wiki_entry_id": str(entry["id"]),
                        "preferred_label": entry.get("preferred_label") or "",
                        "definition": entry.get("definition") or "",
                        "significance": entry.get("significance"),
                        "category": entry.get("category"),
                        "items": entry.get("items") or [],
                        "entry_kind": entry.get("entry_kind") or "term",
                        "importance": entry.get("importance") or "supporting",
                        "plan_id": str(plan["id"]),
                        "enabled": bool(plan.get("enabled")),
                        "layout": str(plan.get("layout") or "label_description"),
                        "instructions": str(plan.get("instructions") or ""),
                        "visual": visual,
                        "flashcard": (
                            {
                                "assessment_id": str(card["id"]),
                                "front": str(card.get("front") or ""),
                                "back": str(card.get("back") or ""),
                            }
                            if card
                            else None
                        ),
                        "questions": questions_by_entry.get(str(entry["id"]), []),
                        "scenarios": scenarios_by_entry.get(str(entry["id"]), []),
                    },
                )
            if item_type in {"question", "scenario"} or plan.get("assessment_id"):
                row = assessments.get(str(plan.get("assessment_id") or ""))
                title, body = _item_text(item_type, row, by_id.get(str(plan.get("wiki_entry_id") or "")))
                if item_type == "flashcard" and not plan.get("assessment_id"):
                    continue
                item_views.append(
                    {
                        "plan_id": str(plan["id"]),
                        "item_type": item_type,
                        "assessment_id": plan.get("assessment_id"),
                        "title": title,
                        "body": body,
                        "visual": visual,
                    },
                )
        entry_views.sort(key=lambda item: str(item["preferred_label"]).lower())
        return {**project, "pipeline": pipeline, "entries": entry_views, "items": item_views}

    async def _enqueue(
        self,
        project: dict[str, Any],
        *,
        run_column: str,
        target: str,
        pipeline: list[dict[str, Any]],
        job: str,
        failure: str,
    ) -> dict[str, Any]:
        project_id = str(project["id"])
        run = await self.production_runs.create(
            {
                "workspace_id": project["workspace_id"],
                "owner_id": project["owner_id"],
                "label": project["title"],
                "source_ids": [project["source_id"]],
                "target_artifacts": [target],
                "pipeline": pipeline,
                "status": "queued",
            },
        )
        run_id = str(run["id"])
        changes: dict[str, Any] = {"status": "drafting", run_column: run_id, "error": None}
        if job == "draft":
            changes["visual_run_id"] = None
        updated = await self.projects.update(project_id, changes)
        try:
            enqueue_knowledge_run(self.settings, run_id, job)
        except Exception as exc:
            logger.exception("Failed to enqueue knowledge %s for %s", job, project_id)
            await self.production_runs.update(run_id, {"status": "failed", "error": str(exc)})
            restored = "composing" if job == "draft" else "ready"
            await self.projects.update(project_id, {"status": restored, "error": failure})
            raise KnowledgeProjectError(failure) from exc
        return updated or project

    async def _assessments_by_id(self, project_id: str) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for table in ("flashcards", "quizzes", "scenarios"):
            for row in await self.projects.list_assessments(table, project_id):
                indexed[str(row["id"])] = row
        return indexed

    async def _sign_paths(self, paths: set[str], storage: SupabaseStorageClient) -> dict[str, str]:
        signed: dict[str, str] = {}
        for path in paths:
            signed[path] = await storage.create_signed_url(
                bucket=self.settings.sources_bucket,
                path=path,
                expires_in=self.settings.signed_url_expires_seconds,
            )
        return signed

    @staticmethod
    def _visual_paths(plans: list[dict[str, Any]]) -> set[str]:
        paths: set[str] = set()
        for plan in plans:
            visual = plan.get("visual")
            path = storage_path_of(visual if isinstance(visual, dict) else None)
            if path:
                paths.add(path)
        return paths

    @staticmethod
    def _active_run_id(project: dict[str, Any]) -> str | None:
        status = project.get("status")
        if status == "structuring":
            return project.get("structure_run_id")
        if status == "drafting":
            return project.get("visual_run_id") or project.get("draft_run_id")
        if status == "failed":
            return project.get("draft_run_id") or project.get("structure_run_id")
        return project.get("visual_run_id") or project.get("draft_run_id") or project.get("structure_run_id")

    @staticmethod
    def _require_status(project: dict[str, Any], expected: str) -> None:
        if project.get("status") != expected:
            raise KnowledgeProjectError(f"This project is {project.get('status')}, not {expected}.")

    @staticmethod
    def _require_visual_edit(project: dict[str, Any], plan: dict[str, Any]) -> None:
        status = project.get("status")
        item_type = plan.get("item_type")
        if status == "composing" and item_type == "flashcard":
            return
        if status == "ready":
            return
        raise KnowledgeProjectError("Images can be added while composing flashcards or after a draft is ready.")


def _concept(entry: dict[str, Any]) -> ConceptCard:
    importance = str(entry.get("importance") or "supporting")
    if importance not in {"essential", "supporting", "contextual"}:
        importance = "supporting"
    return ConceptCard(
        wiki_id=str(entry["id"]),
        preferred_label=str(entry.get("preferred_label") or ""),
        definition=str(entry.get("definition") or ""),
        entry_kind=str(entry.get("entry_kind") or "term"),
        significance=entry.get("significance"),
        items=entry.get("items") or [],
        aliases=entry.get("aliases") or [],
        importance=importance,
    )


def _cited_wiki_ids(row: dict[str, Any]) -> set[str]:
    cited: set[str] = set()
    for citation in row.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        uri = str(citation.get("uri") or "")
        if uri.startswith("wiki://"):
            cited.add(uri.removeprefix("wiki://"))
    return cited


def _assessment_rows(
    project: dict[str, Any],
    *,
    kind: str,
    category: str,
    item_format: str,
    generated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in generated:
        shared = {
            "workspace_id": project["workspace_id"],
            "source_id": project["source_id"],
            "knowledge_project_id": project["id"],
            "difficulty": item.get("difficulty") or "medium",
            "bloom_level": item.get("bloom_level"),
            "citations": [
                {"uri": f"wiki://{wiki_id}", "type": "wiki"} for wiki_id in item.get("wiki_ids_cited") or []
            ],
            "origin": {"source": "knowledge_batch", "category": category, "format": item_format},
        }
        if kind == "question":
            rows.append(
                {
                    **shared,
                    "question": item["question"],
                    "question_type": item.get("question_type") or item_format,
                    "options": item.get("options") or [],
                    "correct_answer": item["correct_answer"],
                    "answer_pool": item.get("answer_pool") or {},
                    "explanation": item.get("explanation"),
                    "subtype": item_format,
                },
            )
        else:
            rows.append(
                {
                    **shared,
                    "title": item["title"],
                    "prompt": item["prompt"],
                    "context": item.get("context"),
                    "evaluation_criteria": item.get("evaluation_criteria") or [],
                    "subtype": item_format,
                },
            )
    return rows


def _flashcard_row(project: dict[str, Any], plan: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    layout = str(plan.get("layout") or "label_description")
    visual = plan.get("visual") if isinstance(plan.get("visual"), dict) else None
    front, back = flashcard_sides(entry, layout)
    draft = plan.get("draft") if isinstance(plan.get("draft"), dict) else {}
    card = draft.get("card") if isinstance(draft.get("card"), dict) else None
    if card and str(card.get("front") or "").strip() and str(card.get("back") or "").strip():
        front, back = str(card["front"]).strip(), str(card["back"]).strip()
    card_visual = None
    if visual and layout_needs_image(layout):
        card_visual = {**visual, "placement": PLACEMENT_FOR_LAYOUT[layout]}
    return {
        "workspace_id": project["workspace_id"],
        "source_id": project["source_id"],
        "knowledge_project_id": str(project["id"]),
        "front": front,
        "back": back,
        "difficulty": "medium",
        "tags": [str(entry["category"])] if entry.get("category") else [],
        "citations": [{"uri": f"wiki://{entry['id']}", "type": "wiki"}],
        "visual": card_visual,
        "origin": {"source": "wiki_entry", "layout": layout, "edited": bool(card)},
        "subtype": "basic",
    }


def _check_format(kind: str, item_format: str) -> None:
    if kind == "question" and item_format not in QUESTION_FORMATS:
        raise KnowledgeProjectError("Choose a question format.")
    if kind == "scenario" and item_format not in SCENARIO_FORMATS:
        raise KnowledgeProjectError("Choose a scenario format.")
    if kind not in TABLE_FOR_KIND:
        raise KnowledgeProjectError("Choose questions or scenarios.")


def _check_bloom(bloom_level: str) -> None:
    if bloom_level and bloom_level not in BLOOM_LEVELS:
        raise KnowledgeProjectError("Choose a cognitive level.")


def _join_notes(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _category_note(project: dict[str, Any], category: str) -> str:
    batch = project.get("batch_instructions")
    if not isinstance(batch, dict):
        return ""
    return str(batch.get(category) or "")


def _stems(kind: str, rows: list[dict[str, Any]]) -> list[str]:
    """Question stems or scenario prompts already written for these rows."""
    key = "question" if kind == "question" else "prompt"
    stems: list[str] = []
    for row in rows:
        text = str(row.get(key) or "").strip()
        if text:
            stems.append(text)
    return stems


def _question_changes(payload: dict[str, Any], *, item_format: str) -> dict[str, Any]:
    question = " ".join(str(payload.get("question") or "").split())
    if not question:
        raise KnowledgeProjectError("Write the question.")
    try:
        pool = AnswerPool.model_validate(payload.get("answer_pool") or {})
        pool.correct = [" ".join(text.split()) for text in pool.correct if text.strip()]
        for row in pool.distractors:
            row.text = " ".join(row.text.split())
        pool.distractors = [row for row in pool.distractors if row.text]
        validate_pool(pool, item_format)
        rendered = _default_render(question, pool, item_format)
    except AnswerPoolError as exc:
        raise KnowledgeProjectError(str(exc)) from exc
    return {
        "question": rendered.question or question,
        "subtype": item_format,
        "question_type": normalize_question_type(item_format),
        "options": rendered.options,
        "correct_answer": rendered.correct_answer,
        "answer_pool": pool.model_dump(),
        "explanation": (str(payload.get("explanation") or "").strip() or None),
    }


def _default_render(question: str, pool: AnswerPool, item_format: str) -> Draw:
    """One deterministic draw stored on the row for readers without pool support."""
    if item_format == TRUE_FALSE:
        if question in pool.correct:
            return Draw(question=question, options=list(TRUE_FALSE_OPTIONS), correct_answer="True")
        if any(row.text == question for row in pool.distractors):
            return Draw(question=question, options=list(TRUE_FALSE_OPTIONS), correct_answer="False")
        return draw(pool, item_format, random.Random(0))
    picked = draw(pool, item_format, random.Random(zlib.crc32(question.encode("utf-8"))))
    return Draw(options=picked.options, correct_answer=picked.correct_answer)


def _scenario_changes(payload: dict[str, Any], *, item_format: str) -> dict[str, Any]:
    title = " ".join(str(payload.get("title") or "").split())
    prompt = str(payload.get("prompt") or "").strip()
    if not title or not prompt:
        raise KnowledgeProjectError("Scenarios need a title and a prompt.")
    criteria = [str(item).strip() for item in payload.get("evaluation_criteria") or [] if str(item).strip()]
    return {
        "title": title,
        "prompt": prompt,
        "context": (str(payload.get("context") or "").strip() or None),
        "evaluation_criteria": criteria,
        "subtype": item_format,
    }


def _question_view(plan: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": str(plan["id"]),
        "assessment_id": str(row["id"]),
        "question": str(row.get("question") or ""),
        "subtype": str(row.get("subtype") or row.get("question_type") or "multiple_choice"),
        "question_type": str(row.get("question_type") or "multiple_choice"),
        "options": row.get("options") or [],
        "correct_answer": str(row.get("correct_answer") or ""),
        "answer_pool": row.get("answer_pool") if isinstance(row.get("answer_pool"), dict) else {},
        "bloom_level": row.get("bloom_level"),
        "explanation": row.get("explanation"),
        "difficulty": str(row.get("difficulty") or "medium"),
        "draft": plan.get("draft") if isinstance(plan.get("draft"), dict) else None,
    }


def _scenario_view(plan: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": str(plan["id"]),
        "assessment_id": str(row["id"]),
        "title": str(row.get("title") or ""),
        "prompt": str(row.get("prompt") or ""),
        "context": row.get("context"),
        "evaluation_criteria": row.get("evaluation_criteria") or [],
        "subtype": str(row.get("subtype") or "decision_prompt"),
        "bloom_level": row.get("bloom_level"),
        "difficulty": str(row.get("difficulty") or "medium"),
        "draft": plan.get("draft") if isinstance(plan.get("draft"), dict) else None,
    }


def _structured_upload(
    filename: str | None,
    content_type: str | None,
    content: bytes | None,
) -> tuple[str, str] | None:
    """Return ``(text, filename)`` when the upload is structured JSON."""
    if not content:
        return None
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    name = filename or ""
    if not name.lower().endswith(".json") and declared not in {"application/json", "text/json"}:
        return None
    safe_name = sanitize_upload_filename(name or "notes.json")
    if not safe_name.lower().endswith(".json"):
        safe_name = f"{safe_name}.json"
    try:
        text = content.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise KnowledgeProjectError(f"Could not decode '{safe_name}' as UTF-8 text.") from exc
    try:
        require_structured_notes(text, filename=safe_name)
    except StructuredNotesError as exc:
        raise KnowledgeProjectError(str(exc)) from exc
    return text, safe_name


def _candidates(notes: StructuredNotes, source_id: str) -> list[WikiCandidate]:
    evidence = [{"source_id": source_id}]
    origin = {"source": "structured_notes"}
    candidates: list[WikiCandidate] = []
    for entry in notes.entries:
        importance = str(entry.get("importance") or "supporting")
        if importance not in {"essential", "supporting", "contextual"}:
            importance = "supporting"
        candidates.append(
            WikiCandidate(
                label=str(entry["label"]),
                definition=str(entry.get("definition") or ""),
                entry_kind=entry.get("entry_kind") or "term",
                significance=entry.get("significance"),
                category=entry.get("category"),
                items=entry.get("items") or [],
                aliases=entry.get("aliases") or [],
                prerequisite_labels=entry.get("prerequisite_labels") or [],
                pronunciation=entry.get("pronunciation"),
                importance=importance,
                evidence=evidence,
                origin=origin,
            ),
        )
    return candidates


def _item_text(
    item_type: str,
    row: dict[str, Any] | None,
    entry: dict[str, Any] | None,
) -> tuple[str, str]:
    if row and item_type == "flashcard":
        return str(row.get("front") or ""), str(row.get("back") or "")
    if row and item_type == "question":
        return str(row.get("question") or ""), str(row.get("correct_answer") or "")
    if row and item_type == "scenario":
        return str(row.get("title") or ""), str(row.get("prompt") or "")
    if entry:
        return str(entry.get("preferred_label") or ""), str(entry.get("definition") or "")
    return "", ""
