from __future__ import annotations

import io
import uuid
from typing import Any

import fitz
from PIL import Image

from app.mathesys.study_material.images import ImageRequest, ImageResult
from app.mathesys.study_material.printer import FitReport
from app.pipeline import build_study_material_pipeline
from app.services.llm.base import LLMCompletionResult
from app.worker.study_material_runner import StudyMaterialRunner


def _png(width: int = 1536, height: int = 1024) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _letter_pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=612, height=792)
    payload = document.tobytes()
    document.close()
    return payload


class FakeDb:
    def __init__(self) -> None:
        self.run = {
            "id": "run-1",
            "workspace_id": "ws-1",
            "pipeline": build_study_material_pipeline(),
            "status": "queued",
        }
        self.material = {
            "id": "mat-1",
            "workspace_id": "ws-1",
            "title": "Land Navigation",
            "slug": "land-navigation",
            "theme_id": "usmc",
            "template_id": "branded-sheet",
            "options": {"logo_locked": True, "logo_id": "ega", "footer_text": "", "section_notes": {}},
            "status": "generating",
            "layout": {},
            "production_run_id": "run-1",
            "artifact_id": None,
        }
        self.components = [
            {"id": "c-text", "section_id": "body", "component_type": "text", "position": 3,
             "instructions": "Explain terrain association.", "settings": {}, "files": [], "active_version_id": None},
            {"id": "c-diagram", "section_id": "body", "component_type": "diagram", "position": 1,
             "instructions": "Five terrain features.", "settings": {}, "files": [], "active_version_id": None},
            {"id": "c-image", "section_id": "body", "component_type": "image", "position": 2,
             "instructions": "A compass on a map.", "settings": {"provider": "openai"},
             "files": [{"id": "f1", "filename": "notes.md", "mime_type": "text/markdown", "storage_path": "ws/notes.md"}],
             "active_version_id": None},
        ]
        self.versions: list[dict[str, Any]] = []
        self.stage_runs: dict[str, dict[str, Any]] = {}
        self.artifacts: list[dict[str, Any]] = []

    def get_production_run(self, run_id: str) -> dict[str, Any] | None:
        return dict(self.run) if run_id == self.run["id"] else None

    def update_production_run(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.run.update(payload)
        return dict(self.run)

    def get_study_material_for_run(self, run_id: str) -> dict[str, Any] | None:
        return dict(self.material)

    def get_study_material(self, material_id: str) -> dict[str, Any] | None:
        return dict(self.material)

    def update_study_material(self, material_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.material.update(payload)
        return dict(self.material)

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        return {"id": workspace_id, "slug": "ocs-prep"}

    def list_workspace_stage_settings(self, workspace_id: str) -> list[dict[str, Any]]:
        return []

    def list_study_material_components(self, material_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.components]

    def list_study_material_versions(self, material_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.versions]

    def insert_study_material_version(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {"id": uuid.uuid4().hex, **payload}
        self.versions.append(row)
        return dict(row)

    def update_study_material_component(self, component_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = next(item for item in self.components if item["id"] == component_id)
        row.update(payload)
        return dict(row)

    def create_stage_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {"id": f"sr-{len(self.stage_runs) + 1}", **payload}
        self.stage_runs[row["id"]] = row
        return dict(row)

    def update_stage_run(self, stage_run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.stage_runs[stage_run_id].update(payload)
        return dict(self.stage_runs[stage_run_id])

    def sum_stage_run_costs(self, run_id: str) -> float:
        return round(sum(float(row.get("cost_usd") or 0) for row in self.stage_runs.values()), 6)

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        return next((row for row in self.artifacts if row["id"] == artifact_id), None)

    def create_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {"id": "art-1", **payload}
        self.artifacts.append(row)
        return row

    def update_artifact(self, artifact_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.get_artifact(artifact_id)
        assert row is not None
        row.update(payload)
        return row


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {"ws/notes.md": b"# Terrain\nHill, valley, ridge, saddle, depression."}

    def download(self, path: str, *, bucket: str | None = None) -> bytes:
        return self.objects[path]

    def upload(self, path: str, content: bytes, *, bucket: str | None = None, content_type: str = "", upsert: bool = True) -> None:
        self.objects[path] = content


class FakeRenderer:
    def __init__(self, overflow_passes: int = 0) -> None:
        self.overflow_passes = overflow_passes
        self.measured: list[str] = []

    def __enter__(self) -> FakeRenderer:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def measure(self, html: str, *, width_in: float, height_in: float) -> FitReport:
        self.measured.append(html)
        overflow = len(self.measured) <= self.overflow_passes
        return FitReport(
            page_width_in=width_in,
            page_height_in=height_in,
            sections=[{"id": "body", "overflow": False}],
            components=[{"id": "c-text", "type": "text", "section": "body", "overflow": overflow, "collapsed": False}],
            images=[{"id": "c-image", "loaded": True, "dpi": 300}],
        )

    def print_pdf(self, html: str, *, width_in: float, height_in: float) -> bytes:
        return _letter_pdf()


class FakeImageClient:
    provider = "openai"
    model = "gpt-image-2.5-flare"

    def __init__(self) -> None:
        self.requests: list[ImageRequest] = []

    def generate(self, request: ImageRequest) -> ImageResult:
        self.requests.append(request)
        return ImageResult(
            data=_png(),
            mime_type="image/png",
            width=1536,
            height=1024,
            model=self.model,
            provider=self.provider,
            token_usage={"input_tokens": 100, "output_tokens": 4000, "total_tokens": 4100},
            settings={"size": "1536x1024"},
        )


class Completer:
    def __init__(self, content: dict[str, Any]) -> None:
        self.content = content
        self.prompts: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None) -> LLMCompletionResult:
        self.prompts.append(user_prompt)
        return LLMCompletionResult(
            content=self.content,
            model="test-model",
            provider="openai",
            token_usage={"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200},
        )


class StudyMaterialCompleter:
    """One action serves diagrams and text; pick the payload from the prompt."""

    def __init__(self, diagram: dict[str, Any], text: dict[str, Any]) -> None:
        self.diagram = diagram
        self.text = text
        self.prompts: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None) -> LLMCompletionResult:
        self.prompts.append(user_prompt)
        content = self.text if "html" in system_prompt else self.diagram
        return LLMCompletionResult(
            content=content,
            model="test-model",
            provider="openai",
            token_usage={"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200},
        )


def _runner(db: FakeDb, renderer: FakeRenderer, image_client: FakeImageClient, completers: dict[str, Completer | StudyMaterialCompleter]) -> StudyMaterialRunner:
    return StudyMaterialRunner(
        db=db,  # type: ignore[arg-type]
        storage=FakeStorage(),  # type: ignore[arg-type]
        renderer_factory=lambda: renderer,
        image_client_factory=lambda provider, model: image_client,
        completer_factory=lambda action: completers[action],
    )


def _completers() -> dict[str, Completer | StudyMaterialCompleter]:
    return {
        "study_material": StudyMaterialCompleter(
            diagram={
                "caption": "Five major terrain features",
                "layout": "hierarchy",
                "nodes": [{"id": "t", "label": "Terrain"}, {"id": "h", "label": "Hill"}, {"id": "v", "label": "Valley"}],
                "connections": [{"from": "t", "to": "h"}, {"from": "t", "to": "v"}],
            },
            text={"html": "<h2>Terrain association</h2><p>Match the map to the ground.</p>", "summary": "How to associate terrain"},
        ),
        "study_material_orchestrator": Completer(
            {"sections": [{"section_id": "body", "arrangement": "stack", "order": ["c-diagram", "c-image", "c-text"], "sizes": {"c-diagram": 30, "c-image": 30}}]},
        ),
    }


def test_generation_runs_visuals_before_text_and_leaves_a_draft() -> None:
    db = FakeDb()
    renderer = FakeRenderer()
    image_client = FakeImageClient()
    completers = _completers()

    _runner(db, renderer, image_client, completers).execute("run-1")

    stage_order = [row["stage_id"] for row in db.stage_runs.values()]
    assert stage_order == ["generate-diagrams", "generate-images", "generate-text", "orchestrate-layout"]
    assert all(row["status"] == "completed" for row in db.stage_runs.values())
    assert db.run["status"] == "completed"
    assert [step["status"] for step in db.run["pipeline"]] == ["completed"] * 6
    assert db.material["status"] == "draft"
    assert db.material["validation"]["issues"] == []
    assert db.material["layout"]["sections"]["body"]["order"] == ["c-diagram", "c-image", "c-text"]
    assert all(row["active_version_id"] for row in db.components)
    assert {row["version"] for row in db.versions} == {1}

    text_prompt = completers["study_material"].prompts[1]
    assert "Five major terrain features" in text_prompt
    assert "A compass on a map." in text_prompt
    assert image_client.requests[0].aspect_ratio in {"16:9", "3:2", "4:3"}
    assert "Hill, valley, ridge" in image_client.requests[0].prompt
    image_run = next(row for row in db.stage_runs.values() if row["stage_id"] == "generate-images")
    assert image_run["api_usage"]["calls"][0]["cost_usd"] == 0.1205


def test_components_with_active_versions_are_kept() -> None:
    db = FakeDb()
    completers = _completers()
    runner = _runner(db, FakeRenderer(), FakeImageClient(), completers)
    runner.execute("run-1")
    db.components[0]["active_version_id"] = None

    runner.execute("run-1")

    assert [row["version"] for row in db.versions if row["component_id"] == "c-text"] == [1, 2]
    assert len([row for row in db.versions if row["component_id"] == "c-diagram"]) == 1
    assert "1 generated" in next(step for step in db.run["pipeline"] if step["step"] == "generate-text")["detail"]


def test_fit_loop_shrinks_text_until_it_fits() -> None:
    db = FakeDb()
    renderer = FakeRenderer(overflow_passes=2)
    _runner(db, renderer, FakeImageClient(), _completers()).execute("run-1")

    assert len(renderer.measured) == 3
    assert db.material["layout"]["sections"]["body"]["font_scale"] == 0.9
    assert db.material["validation"]["issues"] == []


def test_failed_component_fails_the_run_and_material() -> None:
    db = FakeDb()
    completers = _completers()
    study = completers["study_material"]
    assert isinstance(study, StudyMaterialCompleter)
    study.diagram = {"nodes": []}

    runner = _runner(db, FakeRenderer(), FakeImageClient(), completers)
    try:
        runner.execute("run-1")
    except RuntimeError as exc:
        assert "Body diagram failed" in str(exc)
    else:
        raise AssertionError("expected failure")
    assert db.run["status"] == "failed"
    assert db.material["status"] == "failed"


def test_finalize_prints_pdf_into_the_library() -> None:
    db = FakeDb()
    renderer = FakeRenderer()
    runner = _runner(db, renderer, FakeImageClient(), _completers())
    runner.execute("run-1")
    db.material["status"] = "finalizing"

    runner.finalize("mat-1")

    assert db.material["status"] == "finalized"
    artifact = db.artifacts[0]
    assert artifact["artifact_type"] == "study_material"
    assert artifact["source_id"] is None
    assert artifact["storage_path"] == "ocs-prep/study-material/land-navigation/material.pdf"
    assert artifact["manifest"]["title"] == "Land Navigation"
    assert db.run["pipeline"][-1]["step"] == "render-pdf"
    assert db.run["pipeline"][-1]["status"] == "completed"
    assert "Unofficial knowledge for educational use" in renderer.measured[-1]


def test_finalize_blocks_on_validation_issues() -> None:
    db = FakeDb()
    runner = _runner(db, FakeRenderer(), FakeImageClient(), _completers())
    runner.execute("run-1")
    db.material["status"] = "finalizing"
    runner.renderer_factory = lambda: FakeRenderer(overflow_passes=99)

    result = runner.finalize("mat-1")

    assert result["status"] == "draft"
    assert db.material["status"] == "draft"
    assert db.material["validation"]["issues"][0]["code"] == "clipped"
    assert db.artifacts == []
    assert db.run["pipeline"][-1]["status"] == "failed"
