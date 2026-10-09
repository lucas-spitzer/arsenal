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


def structure_knowledge(production_run_id: str) -> dict[str, Any]:
    """Transcribe notes and write wiki entries for a knowledge project."""
    from app.worker.knowledge_runner import KnowledgeRunner

    return KnowledgeRunner().structure(production_run_id)


def draft_knowledge(production_run_id: str) -> dict[str, Any]:
    """Draft the study items selected on a knowledge project and attach images."""
    from app.worker.knowledge_runner import KnowledgeRunner

    return KnowledgeRunner().draft(production_run_id)


def attach_knowledge_visuals(production_run_id: str) -> dict[str, Any]:
    """Copy uploaded images onto the study items for a knowledge project."""
    from app.worker.knowledge_runner import KnowledgeRunner

    return KnowledgeRunner().attach(production_run_id)
