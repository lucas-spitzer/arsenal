from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.pipeline import SUPPORTED_TARGET_ARTIFACTS, build_pipeline
from app.worker.narration_executor import NarrationPaused
from app.worker.pipeline_runner import PipelineContext, PipelineRunner


def test_supported_target_artifacts_include_electronic_book() -> None:
    assert "electronic_book" in SUPPORTED_TARGET_ARTIFACTS


def test_removed_narration_artifacts_are_no_longer_supported() -> None:
    assert "speechify_script" not in SUPPORTED_TARGET_ARTIFACTS
    assert "speechify_audio" not in SUPPORTED_TARGET_ARTIFACTS
    assert "elevenlabs_audio" not in SUPPORTED_TARGET_ARTIFACTS
    assert "eleven_reader_script" not in SUPPORTED_TARGET_ARTIFACTS


def test_build_pipeline_appends_electronic_book_step() -> None:
    pipeline = build_pipeline(["electronic_book"])

    step_names = [step["step"] for step in pipeline]

    assert step_names[-2:] == ["web-enrichment", "create-ebook"]


def test_narration_pipeline_does_not_include_web_enrichment() -> None:
    step_names = [step["step"] for step in build_pipeline(["narration_audio"])]

    assert "web-enrichment" not in step_names
    assert step_names[-1] == "generate-narration"


_RESUME_AT = datetime(2026, 10, 30, 7, 0, tzinfo=UTC)
_PIPELINE = [{"step": "generate-narration", "status": "pending"}]


def _context(*source_ids: str) -> PipelineContext:
    return PipelineContext(
        production_run_id="run-1",
        workspace_id="ws-1",
        sources=[{"id": source_id} for source_id in source_ids],
        target_artifacts=["narration_audio"],
    )


def _paused(stage_run_id: str) -> NarrationPaused:
    return NarrationPaused(
        "Daily Gemini quota reached. Resumes after 2026-10-30 07:00 UTC.",
        resume_at=_RESUME_AT,
        stage_run_id=stage_run_id,
    )


def test_quota_pause_marks_step_waiting_and_holds_later_sources() -> None:
    narration = MagicMock()
    narration.run_for_source.side_effect = [_paused("sr-1")]
    runner = PipelineRunner(db=MagicMock(), storage=MagicMock(), generate_narration=narration)
    context = _context("src-1", "src-2")

    pipeline = runner.run_generate_narration_step(context, _PIPELINE)

    narration.run_for_source.assert_called_once()
    assert context.narration_waiting == {"src-1": "sr-1", "src-2": None}
    assert context.narration_resume_at == _RESUME_AT
    step = pipeline[0]
    assert step["status"] == "waiting"
    assert step["detail"] == (
        "2 source(s) waiting for narration quota; resumes after 2026-10-30 07:00 UTC"
    )


def test_finish_run_queues_resume_instead_of_completing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[tuple[Any, ...]] = []
    monkeypatch.setattr("app.config.get_settings", lambda: "settings")
    monkeypatch.setattr(
        "app.services.queue.enqueue_narration_resume",
        lambda *args: scheduled.append(args),
    )
    db = MagicMock()
    db.sum_stage_run_costs.return_value = 0.25
    runner = PipelineRunner(db=db, storage=MagicMock(), generate_narration=MagicMock())
    context = _context("src-1")
    context.narration_waiting = {"src-1": "sr-1"}
    context.narration_resume_at = _RESUME_AT

    result = runner._finish_run(context, _PIPELINE)

    assert result["status"] == "queued"
    assert scheduled == [("settings", "run-1", {"src-1": "sr-1"}, _RESUME_AT)]
    update = db.update_production_run.call_args.args[1]
    assert update["status"] == "queued"
    assert "completed_at" not in update


def test_resume_narration_continues_paused_stage_run_and_completes() -> None:
    db = MagicMock()
    db.get_production_run.return_value = {
        "id": "run-1",
        "status": "queued",
        "workspace_id": "ws-1",
        "target_artifacts": ["narration_audio"],
        "pipeline": [{"step": "generate-narration", "status": "waiting"}],
    }
    db.get_sources.return_value = [{"id": "src-1"}]
    db.list_workspace_stage_settings.return_value = []
    db.sum_stage_run_costs.return_value = 0.5
    narration = MagicMock()
    narration.run_for_source.return_value = "sr-1"
    runner = PipelineRunner(db=db, storage=MagicMock(), generate_narration=narration)

    result = runner.resume_narration("run-1", {"src-1": "sr-1"})

    assert result["status"] == "completed"
    assert narration.run_for_source.call_args.kwargs["stage_run_id"] == "sr-1"
    first_update = db.update_production_run.call_args_list[0].args[1]
    assert first_update["status"] == "running"
    final = db.update_production_run.call_args.args[1]
    assert final["status"] == "completed"
    assert final["pipeline"][0]["status"] == "completed"


@pytest.mark.parametrize("row", [None, {"id": "run-1", "status": "cancelled"}])
def test_resume_narration_skips_runs_that_are_gone_or_not_queued(
    row: dict[str, Any] | None,
) -> None:
    db = MagicMock()
    db.get_production_run.return_value = row
    narration = MagicMock()
    runner = PipelineRunner(db=db, storage=MagicMock(), generate_narration=narration)

    result = runner.resume_narration("run-1", {"src-1": "sr-1"})

    assert result["message"] == "Narration resume skipped."
    narration.run_for_source.assert_not_called()
    db.update_production_run.assert_not_called()
