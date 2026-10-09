from __future__ import annotations

import json
from typing import Any, Callable

from app.config import get_settings

from app.qngen.canonical_context import (
    ChapterBlueprint,
    ConceptCard,
    format_concepts_for_llm,
)
from app.qngen.context import format_json_block
from app.qngen.skills.shared.skill_loader import load_skill_markdown
from app.services.llm import LLMClient, get_llm_client

_IMPORTANCE_ORDER = {"essential": 0, "supporting": 1, "contextual": 2}

DRAFT_INSTRUCTIONS = """
You are in DRAFT mode. Generate assessment items for the requested artifact type only.
Ground every item in the provided concept cards and evidence segments.
Return valid JSON with a top-level "items" array.
"""

CRITIQUE_INSTRUCTIONS = """
You are in CRITIQUE mode. Review the draft items for grounding, distractor quality,
canonical label usage, and difficulty calibration. Return JSON:
{
  "issues": [{"item_id": "...", "severity": "high|medium|low", "issue": "...", "suggestion": "..."}],
  "overall_quality": "acceptable|needs_revision",
  "summary": "brief critique"
}
"""

REVISE_INSTRUCTIONS = """
You are in REVISE mode. Incorporate the critique and produce improved items.
Return valid JSON with a top-level "items" array using the same schema as the draft.
"""

REPAIR_INSTRUCTIONS = """
You are in REPAIR mode. The listed items cite wiki_ids or source_chunk_ids that
are NOT in this batch, so they will be discarded. For each item, re-ground it
using ONLY the allowed wiki_ids and source_chunk_ids provided, keeping its
"item_id" unchanged. If an item genuinely cannot be grounded in the allowed
evidence, omit it. Return valid JSON with a top-level "items" array using the
same schema as the draft.
"""


def _critique_supporting_enabled() -> bool:
    return get_settings().qngen.critique_supporting


def _batch_needs_critique(batch: list[ConceptCard]) -> bool:
    if not batch:
        return False

    if any(concept.importance == "essential" for concept in batch):
        return True

    if _critique_supporting_enabled():
        return any(concept.importance == "supporting" for concept in batch)

    return False


def _merge_token_usage(
    accumulated: dict[str, int],
    addition: dict[str, int],
) -> dict[str, int]:
    for key, value in addition.items():
        accumulated[key] = accumulated.get(key, 0) + value
    return accumulated


def _format_objectives(learning_objectives: list[dict[str, Any]]) -> str:
    if not learning_objectives:
        return "[]"
    return json.dumps(learning_objectives, indent=2)


def _ungrounded_items(
    items: list[dict[str, Any]],
    *,
    wiki_ids: set[str],
    segment_ids: set[str],
) -> list[dict[str, Any]]:
    """Items citing any wiki_id or segment_id outside the batch."""
    flagged: list[dict[str, Any]] = []
    for item in items:
        cited_wiki = set(item.get("wiki_ids_cited") or [])
        cited_segments = set(item.get("source_chunk_ids") or [])
        if cited_wiki - wiki_ids or cited_segments - segment_ids:
            flagged.append(item)
    return flagged


def _repair_ungrounded_items(
    *,
    items: list[dict[str, Any]],
    concepts: list[ConceptCard],
    artifact_type: str,
    skill_md: str,
    llm: LLMClient,
    token_usage: dict[str, int],
) -> list[dict[str, Any]]:
    """Bounded generate→check→revise loop for grounding only.

    Re-prompts the model to fix items whose citations fall outside the batch,
    one round at a time, up to ``qngen.max_repair_turns``. Deliberately narrow:
    it never touches per-concept caps or answer coercion (handled
    deterministically in the validator), so it cannot re-feed intentionally
    pruned items.
    """
    max_turns = get_settings().qngen.max_repair_turns
    if max_turns <= 0 or not items:
        return items

    wiki_ids = {concept.wiki_id for concept in concepts}
    segment_ids = {
        segment_id
        for concept in concepts
        for segment_id in concept.evidence_segment_ids
    }

    for _ in range(max_turns):
        flagged = _ungrounded_items(items, wiki_ids=wiki_ids, segment_ids=segment_ids)
        if not flagged:
            break
        flagged_ids = {item.get("item_id") for item in flagged}

        repair_result = llm.complete_json(
            system_prompt=f"{skill_md}\n\n{REPAIR_INSTRUCTIONS}",
            user_prompt=f"""Allowed wiki_ids:
{json.dumps(sorted(wiki_ids), indent=2)}

Allowed source_chunk_ids:
{json.dumps(sorted(segment_ids), indent=2)}

Concept evidence for this batch:
{format_concepts_for_llm(concepts)}

Items to re-ground (keep each item_id; omit any you cannot ground):
{json.dumps({"items": flagged}, indent=2)}""",
        )
        _merge_token_usage(token_usage, repair_result.token_usage)

        revised_by_id: dict[str, dict[str, Any]] = {}
        for revised in repair_result.content.get("items") or []:
            revised["type"] = artifact_type
            item_id = revised.get("item_id")
            if item_id:
                revised_by_id[item_id] = revised

        if not revised_by_id:
            break

        merged: list[dict[str, Any]] = []
        changed = False
        for item in items:
            item_id = item.get("item_id")
            replacement = revised_by_id.get(item_id)
            if replacement is not None and item_id in flagged_ids:
                merged.append(replacement)
                changed = True
            else:
                merged.append(item)
        items = merged
        if not changed:
            break

    return items


def _format_count_band(
    artifact_type: str,
    count_band: tuple[int, int] | None,
) -> str:
    if not count_band:
        return ""
    minimum, maximum = count_band
    return (
        f"\nItem budget for this batch: generate between {minimum} and {maximum} "
        f"{artifact_type} items, choosing the number by how much the batch supports "
        "— prefer fewer strong items over padding to the maximum.\n"
    )


def _author_note(
    *,
    artifact_type: str,
    required_subtype: str,
    instructions: str,
    bloom_level: str,
    items_per_concept: int | None,
    avoid_stems: list[str],
    context_concepts: list[ConceptCard],
) -> str:
    note = ""
    if required_subtype.strip():
        note += f"\nEvery item must use subtype \"{required_subtype.strip()}\".\n"
    if bloom_level.strip():
        note += (
            f"\nTarget cognitive level: {bloom_level.strip()}. Set \"bloom_level\" to this value "
            "and write the item so it demands that level, not plain recall.\n"
        )
    if items_per_concept:
        plural = "item" if items_per_concept == 1 else "items"
        note += (
            f"\nWrite exactly {items_per_concept} {artifact_type} {plural} per concept in this batch. "
            "Each must take a different angle (definition, contrast with a sibling, application, membership).\n"
        )
    if avoid_stems:
        listed = "\n".join(f"- {stem}" for stem in avoid_stems if stem.strip())
        note += f"\nAlready asked (do not repeat or lightly reword these):\n{listed}\n"
    if context_concepts:
        note += (
            "\nDistractor candidates (sibling concepts from the same category; do NOT write items "
            "about them, cite them only in distractors):\n"
            f"{format_concepts_for_llm(context_concepts)}\n"
        )
    if instructions.strip():
        note += f"\nAuthor instructions:\n{instructions.strip()}\n"
    return note


def run_skill_batch(
    *,
    skill_name: str,
    artifact_type: str,
    source_metadata: dict[str, Any],
    concepts: list[ConceptCard],
    learning_objectives: list[dict[str, Any]],
    count_band: tuple[int, int] | None = None,
    instructions: str = "",
    required_subtype: str = "",
    bloom_level: str = "",
    items_per_concept: int | None = None,
    avoid_stems: list[str] | None = None,
    context_concepts: list[ConceptCard] | None = None,
    draft_client: LLMClient | None = None,
    critique_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run draft → critique → revise for one concept batch and artifact type.

    ``context_concepts`` are shown only as distractor material; items may not
    be written about them or cite them. ``avoid_stems`` lists questions that
    already exist for these concepts so variants cover new ground.
    """
    draft_llm = draft_client or get_llm_client("qngen_draft")
    critique_llm = critique_client or get_llm_client("qngen_critique")
    skill_md = load_skill_markdown(skill_name)
    author_note = _author_note(
        artifact_type=artifact_type,
        required_subtype=required_subtype,
        instructions=instructions,
        bloom_level=bloom_level,
        items_per_concept=items_per_concept,
        avoid_stems=avoid_stems or [],
        context_concepts=context_concepts or [],
    )

    user_prompt = f"""Source metadata:
{format_json_block(source_metadata)}

Artifact type: {artifact_type}
{_format_count_band(artifact_type, count_band)}
{author_note}
Learning objectives:
{_format_objectives(learning_objectives)}

Canonical concepts for this batch:
{format_concepts_for_llm(concepts)}

Return JSON with a top-level "items" array. Each item must have "type": "{artifact_type}".
Only include fields relevant to {artifact_type} items."""

    draft_result = draft_llm.complete_json(
        system_prompt=f"{skill_md}\n\n{DRAFT_INSTRUCTIONS}",
        user_prompt=user_prompt,
    )

    token_usage = dict(draft_result.token_usage)
    model = draft_result.model
    provider = draft_result.provider
    items = list(draft_result.content.get("items") or [])

    if _batch_needs_critique(concepts):
        draft_json = json.dumps({"items": items}, indent=2)
        critique_result = critique_llm.complete_json(
            system_prompt=f"{skill_md}\n\n{CRITIQUE_INSTRUCTIONS}",
            user_prompt=f"""Draft items to critique:
{draft_json}

Concept batch:
{format_concepts_for_llm(concepts)}""",
        )
        _merge_token_usage(token_usage, critique_result.token_usage)
        model = critique_result.model
        provider = critique_result.provider

        critique = critique_result.content
        if critique.get("overall_quality") == "needs_revision":
            revise_result = draft_llm.complete_json(
                system_prompt=f"{skill_md}\n\n{REVISE_INSTRUCTIONS}",
                user_prompt=f"""Original draft:
{draft_json}

Critique:
{json.dumps(critique, indent=2)}

Concept batch:
{format_concepts_for_llm(concepts)}

Revise the items.""",
            )
            _merge_token_usage(token_usage, revise_result.token_usage)
            model = revise_result.model
            provider = revise_result.provider
            revised = list(revise_result.content.get("items") or [])
            if revised:
                items = revised

    for item in items:
        item["type"] = artifact_type

    items = _repair_ungrounded_items(
        items=items,
        concepts=concepts,
        artifact_type=artifact_type,
        skill_md=skill_md,
        llm=draft_llm,
        token_usage=token_usage,
    )

    items.sort(
        key=lambda row: _IMPORTANCE_ORDER.get(
            next(
                (
                    concept.importance
                    for concept in concepts
                    if concept.wiki_id in (row.get("wiki_ids_cited") or [])
                ),
                "contextual",
            ),
            99,
        ),
    )

    return items, {
        "model": model,
        "provider": provider,
        "token_usage": token_usage,
    }


def run_skill_generation(
    *,
    skill_name: str,
    artifact_type: str,
    source_metadata: dict[str, Any],
    concept_batches: list[list[ConceptCard]],
    learning_objectives: list[dict[str, Any]],
    instructions: str = "",
    required_subtype: str = "",
    bloom_level: str = "",
    items_per_concept: int | None = None,
    avoid_stems: list[str] | None = None,
    context_concepts: list[ConceptCard] | None = None,
    draft_client: LLMClient | None = None,
    critique_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run multi-pass generation across all concept batches."""
    all_items: list[dict[str, Any]] = []
    token_usage: dict[str, int] = {}
    model = ""
    provider = ""

    for batch in concept_batches:
        batch_items, execution = run_skill_batch(
            skill_name=skill_name,
            artifact_type=artifact_type,
            source_metadata=source_metadata,
            concepts=batch,
            learning_objectives=learning_objectives,
            instructions=instructions,
            required_subtype=required_subtype,
            bloom_level=bloom_level,
            items_per_concept=items_per_concept,
            avoid_stems=avoid_stems,
            context_concepts=context_concepts,
            draft_client=draft_client,
            critique_client=critique_client,
        )
        all_items.extend(batch_items)
        model = execution["model"]
        provider = execution.get("provider", provider)
        _merge_token_usage(token_usage, execution["token_usage"])

    return all_items, {
        "model": model,
        "provider": provider,
        "token_usage": token_usage,
        "batch_count": len(concept_batches),
    }


def _objective_payload(chapter: ChapterBlueprint) -> list[dict[str, Any]]:
    return [
        {
            "objective_id": objective.objective_id,
            "statement": objective.statement,
            "bloom_level": objective.bloom_level,
            "concept_labels": objective.concept_labels,
        }
        for objective in chapter.objectives
    ]


def run_blueprinted_generation(
    *,
    skill_name: str,
    artifact_type: str,
    source_metadata: dict[str, Any],
    blueprint: list[ChapterBlueprint],
    concept_filter: Callable[[ConceptCard], bool] | None = None,
    count_band: tuple[int, int] | None = None,
    draft_client: LLMClient | None = None,
    critique_client: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate one focused pass per chapter in the blueprint.

    Each chapter's concepts are optionally narrowed by ``concept_filter`` (e.g.
    essential-only for scenarios), its objectives are passed through, and
    ``count_band`` sets a per-chapter item budget. Chapters left with no concepts
    after filtering are skipped. Shared by the question, scenario, and flashcard
    stages so the per-chapter loop lives in one place.
    """
    all_items: list[dict[str, Any]] = []
    token_usage: dict[str, int] = {}
    model = ""
    provider = ""
    chapters_used = 0

    for chapter in blueprint:
        concepts = [
            concept
            for concept in chapter.concepts
            if concept_filter is None or concept_filter(concept)
        ]
        if not concepts:
            continue

        items, execution = run_skill_batch(
            skill_name=skill_name,
            artifact_type=artifact_type,
            source_metadata=source_metadata,
            concepts=concepts,
            learning_objectives=_objective_payload(chapter),
            count_band=count_band,
            draft_client=draft_client,
            critique_client=critique_client,
        )
        all_items.extend(items)
        model = execution["model"]
        provider = execution.get("provider", provider)
        _merge_token_usage(token_usage, execution["token_usage"])
        chapters_used += 1

    return all_items, {
        "model": model,
        "provider": provider,
        "token_usage": token_usage,
        "batch_count": chapters_used,
        "generation_mode": "blueprint",
    }
