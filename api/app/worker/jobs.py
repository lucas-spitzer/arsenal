from __future__ import annotations

from typing import Any

from app.worker.pipeline_runner import PipelineRunner


def orchestrate_production_run(production_run_id: str) -> dict[str, Any]:
    """Run deterministic ingest steps for a production run."""
    runner = PipelineRunner()
    return runner.execute(production_run_id)
