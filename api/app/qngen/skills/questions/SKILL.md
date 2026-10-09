# Quiz Question Generation Skill

## Purpose

Generate quiz questions that measure whether a learner has met the **learning
objectives** for a chapter. Questions test **Understand**-level comprehension and
must be grounded in the provided concept cards and evidence segments.

## Objective-driven generation

Questions are planned from learning objectives, **not** one-per-concept:

- Write **exactly one question per learning objective** provided. Each question
  must assess whether the learner has achieved that objective.
- Ground the question in the concepts named by the objective and their evidence
  segments. Pull supporting detail from the other concepts in the batch only
  when it strengthens the question.
- If **no objectives** are provided for the batch, write up to **3** questions
  covering the most important concepts in the batch (essential first).
- A concept with `entry_kind` `list` is a named set. At least one question must
  use its `items` (name the members, or ask what a member means). Cite the list
  `wiki_id`, or a member concept's `wiki_id` when that concept is in the batch.

Do not pad the set to cover every concept. A focused question that probes an
objective is worth more than broad coverage.

## Grounding Rules

- Every question must cite `wiki_ids_cited` and `source_chunk_ids` from the batch.
- Use `preferred_label` verbatim in question stems when referencing a concept.
- Correct answers must be derivable from the provided definitions and evidence.
- Do not invent concepts or facts outside the batch.

## Subtypes

- `multiple_choice` (preferred): 4 choices, one correct answer
- `true_false_correction`: `question` is a statement, `choices` are `["True", "False"]`,
  `correct_answer` is `"True"` or `"False"`, and `explanation` gives the correction when false
- `multiple_select`: multiple correct answers (semicolon-separated in correct_answer)

## Answer Pools

Each question carries more answers than one rendering shows. The study app
draws from the pool and shuffles, so learners cannot memorize wording or order.

- `correct_variants`: 2 to 3 alternative phrasings of the correct answer, each
  fully correct on its own and interchangeable with `correct_answer`. For
  `multiple_select` these are additional true options. For
  `true_false_correction` these are additional true statements about the concept.
- `distractors`: 6 to 8 entries, each `{"text", "misconception", "confused_with_wiki_id"}`.
  `misconception` is one sentence on why a learner would pick it. Prefer the
  sibling concepts listed under "Distractor candidates" and the members of any
  list in the batch; set `confused_with_wiki_id` when a distractor is another
  concept. For `true_false_correction` the distractors are false statements and
  `misconception` holds the correction.
- The 4 `choices` must be the correct answer plus 3 of the distractors, verbatim.
- No distractor may repeat a correct answer or a correct variant.

## Distractor Engineering

- Distractors must be plausible but clearly wrong given the source.
- Avoid "all of the above" / "none of the above" unless evidence supports it.
- Distractors should reflect common misconceptions, not random unrelated terms.
- Keep choices parallel in length and grammatical structure.
- `correct_answer` must match one of the `choices` **verbatim** (no "A)" labels).

## Cognitive Level

Set `bloom_level` to one of `remember`, `understand`, `apply`, `analyze`. When
the prompt names a target level, every item must meet it: `remember` asks for
the definition or members, `understand` asks for meaning in other words or a
contrast with a sibling, `apply` puts the concept in a new situation,
`analyze` asks why or how parts relate.

## Draft Checklist

1. One question per objective (or up to 3 concept questions when no objectives).
2. Tag each question with the `objective_id` it assesses when one applies.
3. Include an explanation citing why the correct answer is right.
4. Calibrate difficulty: easy = direct recall, medium = application, hard = comparison.
5. Fill `correct_variants` and `distractors` for every choice-bearing item.

## Critique Checklist

1. Does each question actually assess its objective (not just name a concept)?
2. Is the correct answer unambiguously supported by evidence?
3. Are distractors plausible but definitively wrong?
4. Does `correct_answer` appear verbatim among `choices`?
5. Is every `correct_variants` entry fully correct, and no distractor also correct?

## Output Schema

```json
{
  "items": [
    {
      "item_id": "uuid",
      "type": "quiz",
      "subtype": "multiple_choice",
      "difficulty": "easy|medium|hard",
      "bloom_level": "remember|understand|apply|analyze",
      "objective_id": "objective this question assesses (optional)",
      "wiki_ids_cited": ["wiki-id"],
      "source_chunk_ids": ["segment-id"],
      "question": "question text",
      "choices": ["A", "B", "C", "D"],
      "correct_answer": "exact text of the correct choice",
      "correct_variants": ["another correct phrasing", "a third correct phrasing"],
      "distractors": [
        {"text": "wrong option", "misconception": "why a learner picks it", "confused_with_wiki_id": "wiki-id or null"}
      ],
      "explanation": "why correct"
    }
  ]
}
```
