# Scenario Generation Skill

## Purpose

Generate **tactical decision games (TDGs)**: realistic situations that force the
learner to make a concrete decision under uncertainty and defend it. Scenarios
test **Apply**-level use of the chapter's essential concepts. They are generated
per chapter, not one-per-concept.

## Per-chapter generation

- Produce **1–3 tactical decision games per chapter** — choose the number by how
  many genuinely *decision-worthy* themes the chapter supports. A chapter with
  one strong dilemma yields one TDG; a rich chapter yields up to three.
- Each TDG should center on the essential concept(s) of the chapter. Prefer
  themes that involve a real trade-off, competing options, or a judgment call.
- Do **not** manufacture a scenario for every concept. A weak, decision-free
  prompt is worse than fewer strong ones.
- When a concept has `entry_kind` `list`, the decision must turn on its
  `items`. Cite that list, and cite a member concept when the decision uses one.

## Anatomy of a tactical decision game

- **Situation** (`situation`): a brief, concrete, plausible setup grounded in the
  source's domain. Give the learner the facts, constraints, and the tension —
  incomplete information, time pressure, or competing demands.
- **Decision** (`task`): a clear, forced choice. Use an action verb ("decide",
  "recommend", "prioritize", "choose between"). There must be a real decision
  point, not "explain X".
- **expected_response_elements**: the reasoning a strong answer must show —
  the concept(s) applied, the trade-offs weighed, and a committed decision.
- **rubric**: three tiers (`excellent` / `satisfactory` / `poor`) describing what
  separates a sharp decision from a hand-wavy one.

## Grounding Rules

- Every scenario must cite `wiki_ids_cited` and `source_chunk_ids` from the batch.
- Situations must be plausible extensions of the source, not fabricated doctrine.
- The decision must require *applying* the cited concept(s), not recalling them.
- Do not invent concepts outside the batch.

## Subtypes

- `decision_prompt` (preferred): situation + the decision the learner must make
- `rubric_response`: open response with excellent/satisfactory/poor rubric

## Draft Checklist

1. 1–3 decision-worthy TDGs for the chapter (quality over coverage).
2. Each has a genuine decision point, not an explanation prompt.
3. Cite wiki_ids_cited and source_chunk_ids.
4. Difficulty must be exactly one of `easy`, `medium`, or `hard` — never a
   compound value like `medium-hard`. Use `medium` for single-concept
   application, `hard` for multi-concept trade-offs.

## Critique Checklist

1. Does the scenario force a real decision under uncertainty?
2. Is the situation grounded in the source's domain context?
3. Are expected_response_elements specific and evaluable?
4. Is the rubric meaningfully tiered?

## Output Schema

```json
{
  "items": [
    {
      "item_id": "uuid",
      "type": "scenario",
      "subtype": "decision_prompt",
      "difficulty": "medium|hard",
      "bloom_level": "apply|analyze",
      "wiki_ids_cited": ["wiki-id"],
      "source_chunk_ids": ["segment-id"],
      "title": "short scenario title",
      "situation": "background context and the tension",
      "task": "the decision the learner must make",
      "expected_response_elements": ["element"],
      "rubric": {"excellent": "...", "satisfactory": "...", "poor": "..."}
    }
  ]
}
```
