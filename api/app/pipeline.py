from copy import deepcopy
from typing import Any

# Intellex ingest, structure-based. Replaces the old prepare-document +
# deconstruct-document with four explicit structuring stages:
#   normalize -> trim -> structure -> validate
# Structure produces the chapter/section model (taking over chapter grouping
# from the removed deconstruct-document), and the chunk step turns that model
# into both ndr_segments and document_chapters.
#
# Knowledge no longer comes from an extraction stage: wiki entries are
# produced by the wiki_knowledge production-run stages, then managed in Academy.
BASE_PIPELINE: list[dict[str, Any]] = [
    {
        "step": "store",
        "type": "deterministic",
        "module": "intellex",
        "status": "pending",
    },
    {
        "step": "parse",
        "type": "stage",
        "module": "intellex",
        "stage_id": "parse",
        "stage_version": "1.0",
        "status": "pending",
    },
    {
        "step": "normalize-document",
        "type": "stage",
        "module": "intellex",
        "stage_id": "normalize-document",
        "stage_version": "1.1",
        "status": "pending",
    },
    {
        "step": "trim-document-boundaries",
        "type": "stage",
        "module": "intellex",
        "stage_id": "trim-document-boundaries",
        "stage_version": "1.0",
        "status": "pending",
    },
    {
        "step": "structure-document",
        "type": "stage",
        "module": "intellex",
        "stage_id": "structure-document",
        "stage_version": "1.3",
        "status": "pending",
    },
    {
        "step": "validate-structure",
        "type": "stage",
        "module": "intellex",
        "stage_id": "validate-structure",
        "stage_version": "1.0",
        "status": "pending",
    },
    {
        "step": "chunk",
        "type": "deterministic",
        "module": "intellex",
        "status": "pending",
    },
    {
        "step": "source-research",
        "type": "stage",
        "module": "intellex",
        "stage_id": "source-research",
        "stage_version": "2.1",
        "status": "pending",
    },
    # Verifies the extracted profile against the public record (status,
    # canonical URL, public publication date) via LLM web search. Skipped
    # per-source when the distribution line marks the document non-public.
    {
        "step": "web-enrichment",
        "type": "stage",
        "module": "intellex",
        "stage_id": "web-enrichment",
        "stage_version": "1.0",
        "status": "pending",
    },
]

OPTIONAL_PIPELINE_STEPS: dict[str, dict[str, Any]] = {
    "electronic_book": {
        "step": "create-ebook",
        "type": "stage",
        "module": "mathesys",
        "stage_id": "create-ebook",
        "stage_version": "1.0",
        "status": "pending",
    },
    "narration_audio": {
        "step": "generate-narration",
        "type": "stage",
        "module": "mathesys",
        "stage_id": "generate-narration",
        "stage_version": "1.0",
        "status": "pending",
    },
    "wiki_json": {
        "step": "export-wiki-json",
        "type": "stage",
        "module": "mathesys",
        "stage_id": "export-wiki-json",
        "stage_version": "1.0",
        "status": "pending",
    },
    "study_sheet": {
        "step": "generate-study-sheet",
        "type": "stage",
        "module": "mathesys",
        "stage_id": "generate-study-sheet",
        "stage_version": "1.0",
        "status": "pending",
    },
    "flashcards": {
        "step": "generate-flashcards",
        "type": "stage",
        "module": "qngen",
        "stage_id": "generate-flashcards",
        "stage_version": "2.0",
        "status": "pending",
    },
    "quizzes": {
        "step": "generate-questions",
        "type": "stage",
        "module": "qngen",
        "stage_id": "generate-questions",
        "stage_version": "2.0",
        "status": "pending",
    },
    "scenarios": {
        "step": "generate-scenarios",
        "type": "stage",
        "module": "qngen",
        "stage_id": "generate-scenarios",
        "stage_version": "2.0",
        "status": "pending",
    },
}

# Wiki knowledge is produced by two Intellex stages after ingest, before
# Mathesys/QnGen, so a later QnGen step in the same run can use the new entries.
WIKI_KNOWLEDGE_STEPS: list[dict[str, Any]] = [
    {
        "step": "transcribe-wiki-notes",
        "type": "stage",
        "module": "intellex",
        "stage_id": "transcribe-wiki-notes",
        "stage_version": "1.0",
        "status": "pending",
    },
    {
        "step": "structure-wiki-notes",
        "type": "stage",
        "module": "intellex",
        "stage_id": "structure-wiki-notes",
        "stage_version": "1.0",
        "status": "pending",
    },
]

QNGEN_TARGET_ARTIFACTS = frozenset({"flashcards", "quizzes", "scenarios"})

SUPPORTED_TARGET_ARTIFACTS = frozenset(
    {*OPTIONAL_PIPELINE_STEPS.keys(), "wiki_knowledge"},
)


def derive_qngen_assessment_types(target_artifacts: list[str]) -> list[str]:
    return [
        artifact
        for artifact in ("flashcards", "quizzes", "scenarios")
        if artifact in target_artifacts
    ]


def build_pipeline(target_artifacts: list[str]) -> list[dict[str, Any]]:
    pipeline = [deepcopy(step) for step in BASE_PIPELINE]

    if "wiki_knowledge" in target_artifacts:
        pipeline.extend(deepcopy(step) for step in WIKI_KNOWLEDGE_STEPS)

    for artifact in target_artifacts:
        if artifact == "wiki_knowledge":
            continue
        optional_step = OPTIONAL_PIPELINE_STEPS.get(artifact)

        if optional_step:
            pipeline.append(deepcopy(optional_step))

    return pipeline
