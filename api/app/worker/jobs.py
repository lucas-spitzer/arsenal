from __future__ import annotations

from typing import Any

from app.worker.pipeline_runner import PipelineRunner
from app.worker.study_material_runner import StudyMaterialRunner


def orchestrate_production_run(production_run_id: str) -> dict[str, Any]:
    """Run deterministic ingest steps for a production run."""
    runner = PipelineRunner()
    return runner.execute(production_run_id)


def generate_study_material(production_run_id: str) -> dict[str, Any]:
    """Generate components and lay out the draft for a Study Material run."""
    return StudyMaterialRunner().execute(production_run_id)


def finalize_study_material(study_material_id: str) -> dict[str, Any]:
    """Validate the draft and print the final PDF into the Library."""
    return StudyMaterialRunner().finalize(study_material_id)
