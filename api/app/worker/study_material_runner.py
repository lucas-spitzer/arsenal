"""Worker for Study Material production runs and finalization.

Generation order is fixed: diagrams, then images, then text, so text is
written with the visuals it shares a section with already known. The
orchestrator then plans each section and a Chromium fit loop tightens
sizes and text density until every section fits (or reports what does not).
"""

from __future__ import annotations

import base64
import copy
import logging
import mimetypes
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.artifact_paths import (
    STUDY_MATERIAL_FINAL_HTML,
    STUDY_MATERIAL_FINAL_PDF,
    study_material_component_output_path,
    study_material_output_path,
)
from app.mathesys.study_material.assemble import active_version, build_render_input
from app.mathesys.study_material.catalog import Template, Theme, get_template, get_theme
from app.mathesys.study_material.generation import (
    GeneratedComponent,
    LayoutComponent,
    auto_aspect_ratio,
    generate_diagram_component,
    generate_image_component,
    generate_text_component,
    plan_layout,
    text_word_budget,
)
from app.mathesys.study_material.images import get_image_client, resolve_image_settings
from app.mathesys.study_material.inputs import ComponentFile, reference_text
from app.mathesys.study_material.layout import MIN_FONT_SCALE, SectionLayout
from app.mathesys.study_material.printer import ChromiumRenderer, FitReport, HtmlRenderer
from app.mathesys.study_material.prompts import ComponentPromptContext, SiblingSummary
from app.mathesys.study_material.render import render_document
from app.mathesys.study_material.validation import fit_issues, pdf_issues
from app.pipeline import STUDY_MATERIAL_RENDER_STEP
from app.services.llm import (
    get_llm_client,
    overrides_from_rows,
    reset_workspace_overrides,
    set_workspace_overrides,
)
from app.services.stage_run_billing import (
    image_stage_run_completion_fields,
    stage_run_completion_fields,
)
from app.worker.db import WorkerDatabase
from app.worker.pipeline_runner import mark_step
from app.worker.storage import WorkerStorage

logger = logging.getLogger(__name__)

STAGE_VERSION = "1.0"
MODULE = "mathesys"
MAX_FIT_PASSES = 6
FONT_STEP = 0.05
VISUAL_STEP = 5
MIN_VISUAL_SIZE = 25

GENERATION_STEPS: tuple[tuple[str, str, str], ...] = (
    ("diagram", "generate-diagrams", "study_material"),
    ("image", "generate-images", ""),
    ("text", "generate-text", "study_material"),
)
TYPE_NOUNS = {"diagram": "diagram", "image": "image", "text": "text block"}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


@dataclass
class _Job:
    material: dict[str, Any]
    template: Template
    theme: Theme
    workspace_slug: str
    components: list[dict[str, Any]]
    versions: list[dict[str, Any]]
    files: dict[str, list[ComponentFile]] = field(default_factory=dict)
    image_uris: dict[str, str] = field(default_factory=dict)

    @property
    def versions_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(row["id"]): row for row in self.versions}

    def component_label(self, component: dict[str, Any]) -> str:
        section = self.template.section(str(component["section_id"]))
        same = [
            row for row in self.components
            if row["section_id"] == component["section_id"] and row["component_type"] == component["component_type"]
        ]
        suffix = f" {same.index(component) + 1}" if len(same) > 1 else ""
        return f"{section.label} {TYPE_NOUNS[str(component['component_type'])]}{suffix}"


class StudyMaterialRunner:
    def __init__(
        self,
        db: WorkerDatabase | None = None,
        storage: WorkerStorage | None = None,
        *,
        renderer_factory: Callable[[], HtmlRenderer] | None = None,
        image_client_factory: Callable[[str, str], Any] | None = None,
        completer_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.db = db or WorkerDatabase()
        self.storage = storage or WorkerStorage()
        self.renderer_factory = renderer_factory or ChromiumRenderer
        self.image_client_factory = image_client_factory or get_image_client
        self.completer_factory = completer_factory or get_llm_client

    # ------------------------------------------------------------------ loading

    def _load_job(self, material: dict[str, Any]) -> _Job:
        workspace = self.db.get_workspace(str(material["workspace_id"])) or {}
        workspace_slug = str(workspace.get("slug") or "").strip()
        if not workspace_slug:
            raise RuntimeError("Workspace is missing its storage slug.")
        return _Job(
            material=material,
            template=get_template(str(material["template_id"])),
            theme=get_theme(str(material["theme_id"])),
            workspace_slug=workspace_slug,
            components=self.db.list_study_material_components(str(material["id"])),
            versions=self.db.list_study_material_versions(str(material["id"])),
        )

    def _component_files(self, job: _Job, component: dict[str, Any]) -> list[ComponentFile]:
        component_id = str(component["id"])
        if component_id not in job.files:
            job.files[component_id] = [
                ComponentFile(
                    filename=str(item.get("filename") or "file"),
                    mime_type=str(item.get("mime_type") or "application/octet-stream"),
                    content=self.storage.download(str(item["storage_path"])),
                )
                for item in component.get("files") or []
                if item.get("storage_path")
            ]
        return job.files[component_id]

    def _image_data_uri(self, job: _Job, path: str) -> str:
        if path not in job.image_uris:
            mime = mimetypes.guess_type(path)[0] or "image/png"
            encoded = base64.b64encode(self.storage.download(path)).decode("ascii")
            job.image_uris[path] = f"data:{mime};base64,{encoded}"
        return job.image_uris[path]

    # --------------------------------------------------------------- generation

    def _sibling_summary(self, job: _Job, component: dict[str, Any]) -> str:
        version = active_version(component, job.versions_by_id)
        if version is None:
            instructions = " ".join(str(component.get("instructions") or "").split())
            return f"planned; instructions: {instructions[:160] or 'none'}"
        output = version.get("output") or {}
        if component["component_type"] == "text":
            return str(output.get("summary") or f"{output.get('word_count', 0)} words")
        if component["component_type"] == "diagram":
            spec = output.get("spec") or {}
            labels = ", ".join(str(node.get("label")) for node in spec.get("nodes") or [])
            return f"{output.get('caption') or 'diagram'} (nodes: {labels}; aspect {output.get('aspect')})"
        return f"{output.get('alt') or 'image'} (aspect {output.get('aspect')})"

    def _prompt_context(self, job: _Job, component: dict[str, Any]) -> ComponentPromptContext:
        section = job.template.section(str(component["section_id"]))
        siblings = [row for row in job.components if row["section_id"] == section.id and row["id"] != component["id"]]
        files = self._component_files(job, component)
        word_budget = None
        if component["component_type"] == "text":
            section_rows = [row for row in job.components if row["section_id"] == section.id]
            word_budget = text_word_budget(
                job.template,
                section,
                visual_count=sum(1 for row in section_rows if row["component_type"] != "text"),
                text_count=sum(1 for row in section_rows if row["component_type"] == "text"),
            )
        notes = (job.material.get("options") or {}).get("section_notes") or {}
        return ComponentPromptContext(
            title=str(job.material["title"]),
            theme=job.theme,
            template=job.template,
            section=section,
            instructions=str(component.get("instructions") or ""),
            reference_text=reference_text(files),
            siblings=[
                SiblingSummary(
                    component_id=str(row["id"]),
                    component_type=str(row["component_type"]),
                    summary=self._sibling_summary(job, row),
                )
                for row in siblings
            ],
            word_budget=word_budget,
            section_notes=str(notes.get(section.id) or ""),
        )

    def _generate(self, job: _Job, component: dict[str, Any]) -> GeneratedComponent:
        ctx = self._prompt_context(job, component)
        component_type = component["component_type"]
        if component_type == "diagram":
            return generate_diagram_component(ctx, self.completer_factory("study_material"))
        if component_type == "text":
            return generate_text_component(ctx, self.completer_factory("study_material"))

        settings = resolve_image_settings(component.get("settings"))
        aspect = settings["aspect_ratio"]
        if aspect == "auto":
            section_rows = [row for row in job.components if row["section_id"] == component["section_id"]]
            aspect = auto_aspect_ratio(job.template, ctx.section, sibling_count=len(section_rows) - 1)
        client = self.image_client_factory(settings["provider"], settings["model"])
        return generate_image_component(
            ctx,
            client,
            aspect_ratio=aspect,
            quality=settings["quality"],
            image_size=settings["image_size"],
            references=[item for item in self._component_files(job, component) if item.is_image],
        )

    def _store_version(
        self,
        job: _Job,
        component: dict[str, Any],
        generated: GeneratedComponent,
        stage_run_id: str,
    ) -> dict[str, Any]:
        component_id = str(component["id"])
        version_number = 1 + max(
            (int(row["version"]) for row in job.versions if str(row["component_id"]) == component_id),
            default=0,
        )
        output_path = None
        if generated.binary is not None:
            output_path = study_material_component_output_path(
                job.workspace_slug,
                str(job.material["slug"]),
                component_id,
                version_number,
                generated.extension or "png",
            )
            self.storage.upload(output_path, generated.binary, content_type=generated.binary_mime or "image/png")

        version = self.db.insert_study_material_version(
            {
                "component_id": component_id,
                "study_material_id": str(job.material["id"]),
                "workspace_id": str(job.material["workspace_id"]),
                "version": version_number,
                "output": generated.output,
                "output_path": output_path,
                "instructions": str(component.get("instructions") or ""),
                "model": generated.model,
                "provider": generated.provider,
                "settings": {**(component.get("settings") or {}), **generated.settings},
                "theme_id": job.theme.id,
                "file_refs": [
                    {"id": item.get("id"), "filename": item.get("filename"), "storage_path": item.get("storage_path")}
                    for item in component.get("files") or []
                ],
                "stage_run_id": stage_run_id,
            },
        )
        job.versions.append(version)
        updated = self.db.update_study_material_component(component_id, {"active_version_id": version["id"]})
        component.update(updated)
        return version

    def _run_generation_step(
        self,
        job: _Job,
        pipeline: list[dict[str, Any]],
        *,
        component_type: str,
        step_name: str,
    ) -> list[dict[str, Any]]:
        matching = [row for row in job.components if row["component_type"] == component_type]
        pending = [row for row in matching if active_version(row, job.versions_by_id) is None]
        last_stage_run_id: str | None = None

        for component in pending:
            label = job.component_label(component)
            stage_run = self.db.create_stage_run(
                {
                    "production_run_id": job.material["production_run_id"],
                    "workspace_id": job.material["workspace_id"],
                    "stage_id": step_name,
                    "stage_version": STAGE_VERSION,
                    "module": MODULE,
                    "status": "running",
                    "inputs": {
                        "study_material_id": job.material["id"],
                        "component_id": component["id"],
                        "section_id": component["section_id"],
                        "label": label,
                    },
                    "started_at": utc_now_iso(),
                },
            )
            stage_run_id = str(stage_run["id"])
            last_stage_run_id = stage_run_id
            try:
                generated = self._generate(job, component)
                version = self._store_version(job, component, generated, stage_run_id)
                if component_type == "image":
                    billing = image_stage_run_completion_fields(
                        provider=generated.provider,
                        model=generated.model,
                        token_usage=generated.token_usage,
                    )
                else:
                    billing = stage_run_completion_fields(
                        {
                            "model": generated.model,
                            "provider": generated.provider,
                            "token_usage": generated.token_usage,
                        },
                    )
                self.db.update_stage_run(
                    stage_run_id,
                    {
                        "status": "completed",
                        "output": {
                            "summary": f"{label}: {generated.summary}"[:300],
                            "component_id": component["id"],
                            "version_id": version["id"],
                            "version": version["version"],
                        },
                        "promoted": {"study_material_component_version_ids": [version["id"]]},
                        **billing,
                        "completed_at": utc_now_iso(),
                    },
                )
            except Exception as exc:
                logger.exception("Study material component %s failed", component["id"])
                self.db.update_stage_run(
                    stage_run_id,
                    {"status": "failed", "error": str(exc), "completed_at": utc_now_iso()},
                )
                raise RuntimeError(f"{label} failed: {exc}") from exc

        noun = TYPE_NOUNS[component_type]
        if not matching:
            detail = f"No {noun}s"
        else:
            parts = [f"{len(pending)} generated"] if pending else []
            if len(matching) - len(pending):
                parts.append(f"{len(matching) - len(pending)} kept")
            detail = f"{_plural(len(matching), noun)}: {', '.join(parts)}"
        return mark_step(
            pipeline,
            step_name,
            status="completed",
            stage_run_id=last_stage_run_id,
            detail=detail,
        )

    # ------------------------------------------------------------------ layout

    def _render(self, job: _Job, layouts: dict[str, SectionLayout] | None) -> str:
        data = build_render_input(
            job.material,
            job.components,
            job.versions_by_id,
            image_src=lambda path: self._image_data_uri(job, path),
            layout_override=layouts,
        )
        return render_document(data)

    def _fit(
        self,
        job: _Job,
        layouts: dict[str, SectionLayout],
        renderer: HtmlRenderer,
    ) -> tuple[dict[str, SectionLayout], FitReport]:
        visual_ids = {str(row["id"]) for row in job.components if row["component_type"] != "text"}
        report: FitReport | None = None
        for attempt in range(MAX_FIT_PASSES):
            report = renderer.measure(
                self._render(job, layouts),
                width_in=job.template.width_in,
                height_in=job.template.height_in,
            )
            over = report.overflowing_sections() & set(layouts)
            if not over or attempt == MAX_FIT_PASSES - 1:
                break
            changed = False
            for section_id in over:
                layout = layouts[section_id]
                for cid, size in list(layout.sizes.items()):
                    if cid in visual_ids and size > MIN_VISUAL_SIZE:
                        layout.sizes[cid] = max(MIN_VISUAL_SIZE, size - VISUAL_STEP)
                        changed = True
                if layout.font_scale > MIN_FONT_SCALE:
                    layout.font_scale = round(max(MIN_FONT_SCALE, layout.font_scale - FONT_STEP), 3)
                    changed = True
            if not changed:
                break
        assert report is not None
        return layouts, report

    def _component_labels(self, job: _Job) -> dict[str, str]:
        return {str(row["id"]): job.component_label(row) for row in job.components}

    def _run_orchestrate_step(self, job: _Job, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stage_run = self.db.create_stage_run(
            {
                "production_run_id": job.material["production_run_id"],
                "workspace_id": job.material["workspace_id"],
                "stage_id": "orchestrate-layout",
                "stage_version": STAGE_VERSION,
                "module": MODULE,
                "status": "running",
                "inputs": {"study_material_id": job.material["id"], "component_count": len(job.components)},
                "started_at": utc_now_iso(),
            },
        )
        stage_run_id = str(stage_run["id"])
        try:
            by_section: dict[str, list[LayoutComponent]] = {}
            versions = job.versions_by_id
            for row in job.components:
                version = active_version(row, versions)
                output = (version or {}).get("output") or {}
                by_section.setdefault(str(row["section_id"]), []).append(
                    LayoutComponent(
                        id=str(row["id"]),
                        component_type=str(row["component_type"]),
                        summary=self._sibling_summary(job, row),
                        aspect=output.get("aspect") if row["component_type"] != "text" else None,
                        words=output.get("word_count") if row["component_type"] == "text" else None,
                    ),
                )
            notes = (job.material.get("options") or {}).get("section_notes") or {}
            plan = plan_layout(
                title=str(job.material["title"]),
                theme=job.theme,
                template=job.template,
                components_by_section=by_section,
                section_notes={str(key): str(value) for key, value in notes.items()},
                completer=self.completer_factory("study_material_orchestrator"),
            )
            with self.renderer_factory() as renderer:
                layouts, report = self._fit(job, plan.sections, renderer)
            issues = fit_issues(report, job.template, component_labels=self._component_labels(job))

            job.material = self.db.update_study_material(
                str(job.material["id"]),
                {
                    "layout": {
                        "sections": {section_id: layout.to_dict() for section_id, layout in layouts.items()},
                        "rationale": plan.rationale,
                    },
                    "validation": {"stage": "draft", "checked_at": utc_now_iso(), "issues": issues},
                    "status": "draft",
                    "error": None,
                },
            )
            completion = plan.completion
            billing = (
                stage_run_completion_fields(
                    {"model": completion.model, "provider": completion.provider, "token_usage": completion.token_usage},
                )
                if completion
                else {}
            )
            detail = "Fits the page" if not issues else f"{_plural(len(issues), 'fit issue')} to review"
            self.db.update_stage_run(
                stage_run_id,
                {
                    "status": "completed",
                    "output": {"summary": detail, "sections": len(layouts), "issues": issues},
                    **billing,
                    "completed_at": utc_now_iso(),
                },
            )
        except Exception as exc:
            self.db.update_stage_run(
                stage_run_id,
                {"status": "failed", "error": str(exc), "completed_at": utc_now_iso()},
            )
            raise
        return mark_step(pipeline, "orchestrate-layout", status="completed", stage_run_id=stage_run_id, detail=detail)

    # --------------------------------------------------------------- entrypoints

    def execute(self, production_run_id: str) -> dict[str, Any]:
        run = self.db.get_production_run(production_run_id)
        if not run:
            raise RuntimeError(f"Production run not found: {production_run_id}")
        material = self.db.get_study_material_for_run(production_run_id)
        if not material:
            raise RuntimeError(f"No study material is attached to production run {production_run_id}.")

        pipeline = copy.deepcopy(run.get("pipeline") or [])
        workspace_id = str(run["workspace_id"])
        self.db.update_production_run(production_run_id, {"status": "running", "error": None})
        self.db.update_study_material(str(material["id"]), {"status": "generating", "error": None})
        override_token = set_workspace_overrides(
            overrides_from_rows(self.db.list_workspace_stage_settings(workspace_id)),
        )
        try:
            job = self._load_job(material)
            for component_type, step_name, _action in GENERATION_STEPS:
                pipeline = self._run_generation_step(
                    job,
                    pipeline,
                    component_type=component_type,
                    step_name=step_name,
                )
                self.db.update_production_run(production_run_id, {"pipeline": pipeline})

            options = job.material.get("options") or {}
            theme_detail = [job.theme.name]
            if options.get("logo_locked"):
                theme_detail.append("logo locked")
            if job.theme.disclaimer:
                theme_detail.append("disclaimer on every card" if job.template.disclaimer == "per_section" else "disclaimer in footer")
            pipeline = mark_step(pipeline, "introduce-theme", status="completed", detail=" · ".join(theme_detail))
            self.db.update_production_run(production_run_id, {"pipeline": pipeline})

            sections_used = {str(row["section_id"]) for row in job.components}
            for row in job.components:
                section = job.template.section(str(row["section_id"]))
                if not section.is_flexible or row["component_type"] not in section.allowed_types:
                    raise RuntimeError(f"{job.component_label(row)} is not allowed in {section.label}.")
            pipeline = mark_step(
                pipeline,
                "organize-components",
                status="completed",
                detail=f"{_plural(len(job.components), 'component')} in {_plural(len(sections_used), 'section')}",
            )
            self.db.update_production_run(production_run_id, {"pipeline": pipeline})

            pipeline = self._run_orchestrate_step(job, pipeline)
            cost_usd = self.db.sum_stage_run_costs(production_run_id)
            self.db.update_production_run(
                production_run_id,
                {"pipeline": pipeline, "status": "completed", "completed_at": utc_now_iso(), "cost_usd": cost_usd},
            )
            return {"production_run_id": production_run_id, "status": "completed"}
        except Exception as exc:
            logger.exception("Study material run %s failed", production_run_id)
            self.db.update_production_run(
                production_run_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "pipeline": pipeline,
                    "completed_at": utc_now_iso(),
                    "cost_usd": self.db.sum_stage_run_costs(production_run_id),
                },
            )
            self.db.update_study_material(str(material["id"]), {"status": "failed", "error": str(exc)})
            raise
        finally:
            reset_workspace_overrides(override_token)

    def finalize(self, material_id: str) -> dict[str, Any]:
        material = self.db.get_study_material(material_id)
        if not material:
            raise RuntimeError(f"Study material not found: {material_id}")
        run_id = str(material.get("production_run_id") or "")
        run = self.db.get_production_run(run_id) if run_id else None
        pipeline = [
            step for step in copy.deepcopy((run or {}).get("pipeline") or []) if step.get("step") != "render-pdf"
        ]
        pipeline.append({**copy.deepcopy(STUDY_MATERIAL_RENDER_STEP), "status": "running"})
        if run:
            self.db.update_production_run(
                run_id,
                {"pipeline": pipeline, "status": "running", "error": None, "completed_at": None},
            )

        def close_run(status: str, step_status: str, detail: str, error: str | None = None) -> None:
            nonlocal pipeline
            pipeline = mark_step(pipeline, "render-pdf", status=step_status, detail=detail)
            if run:
                self.db.update_production_run(
                    run_id,
                    {
                        "pipeline": pipeline,
                        "status": status,
                        "error": error,
                        "completed_at": utc_now_iso(),
                        "cost_usd": self.db.sum_stage_run_costs(run_id),
                    },
                )

        def block(issues: list[dict[str, Any]]) -> dict[str, Any]:
            self.db.update_study_material(
                material_id,
                {
                    "status": "draft",
                    "validation": {"stage": "finalize", "checked_at": utc_now_iso(), "issues": issues},
                },
            )
            close_run("completed", "failed", f"Blocked by {_plural(len(issues), 'validation issue')}")
            return {"study_material_id": material_id, "status": "draft", "issues": issues}

        try:
            job = self._load_job(material)
            template = job.template
            missing = [
                {
                    "code": "missing_component",
                    "message": f"{job.component_label(row)} has no generated content.",
                    "component_id": str(row["id"]),
                    "section_id": str(row["section_id"]),
                }
                for row in job.components
                if active_version(row, job.versions_by_id) is None
            ]
            if missing:
                return block(missing)

            html = self._render(job, None)
            with self.renderer_factory() as renderer:
                report = renderer.measure(html, width_in=template.width_in, height_in=template.height_in)
                issues = fit_issues(report, template, component_labels=self._component_labels(job))
                if issues:
                    return block(issues)
                pdf = renderer.print_pdf(html, width_in=template.width_in, height_in=template.height_in)
            issues = pdf_issues(pdf, template)
            if issues:
                return block(issues)

            slug = str(material["slug"])
            html_path = study_material_output_path(job.workspace_slug, slug, STUDY_MATERIAL_FINAL_HTML)
            pdf_path = study_material_output_path(job.workspace_slug, slug, STUDY_MATERIAL_FINAL_PDF)
            self.storage.upload(html_path, html.encode("utf-8"), content_type="text/html")
            self.storage.upload(pdf_path, pdf, content_type="application/pdf")

            payload = {
                "workspace_id": material["workspace_id"],
                "source_id": None,
                "production_run_id": run_id or None,
                "artifact_type": "study_material",
                "format": "pdf",
                "filename": f"{slug}.pdf",
                "storage_path": pdf_path,
                "file_size_bytes": len(pdf),
                "manifest": {
                    "module": MODULE,
                    "title": material["title"],
                    "theme_id": job.theme.id,
                    "theme_name": job.theme.name,
                    "template_id": template.id,
                    "template_name": template.name,
                    "component_count": len(job.components),
                    "page": {"width_in": template.width_in, "height_in": template.height_in},
                    "html_path": html_path,
                    "study_material_id": material_id,
                },
                "origin": {"study_material_id": material_id, "production_run_id": run_id or None},
            }
            existing_id = material.get("artifact_id")
            existing = self.db.get_artifact(str(existing_id)) if existing_id else None
            artifact = (
                self.db.update_artifact(str(existing["id"]), payload) if existing else self.db.create_artifact(payload)
            )
            self.db.update_study_material(
                material_id,
                {
                    "status": "finalized",
                    "artifact_id": artifact["id"],
                    "final_html_path": html_path,
                    "finalized_at": utc_now_iso(),
                    "error": None,
                    "validation": {"stage": "finalize", "checked_at": utc_now_iso(), "issues": []},
                },
            )
            close_run("completed", "completed", f"1 page · {template.width_in} × {template.height_in} in")
            return {"study_material_id": material_id, "status": "finalized", "artifact_id": artifact["id"]}
        except Exception as exc:
            logger.exception("Study material finalize %s failed", material_id)
            self.db.update_study_material(material_id, {"status": "draft", "error": str(exc)})
            close_run("failed", "failed", "Render failed", error=str(exc))
            raise
