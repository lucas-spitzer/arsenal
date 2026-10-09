# Flashcard Generation Skill

## Purpose

Generate memorization flashcards grounded in canonical wiki concepts and their
evidence segments. Flashcards target the **Remember** level of Bloom's taxonomy.

## Grounding Rules

- Every card must cite at least one `wiki_id` and `source_chunk_id` from the batch.
- Use `preferred_label` verbatim when a term appears on the card front.
- Definitions on the back must align with the provided wiki definition.
- Do not invent concepts outside the batch.

## Subtypes

- `term_definition` (preferred): front = term, back = definition. When `significance` is present, it may follow the definition on the back.
- `list`: front = the list's `preferred_label`. Back = the overview (`definition`) plus the member `name`s, in order.
- `list_item`: front = one member `name`, back = that member's `details`. Cite the list `wiki_id`. Skip a member whose name is already another concept's `preferred_label`; that concept gets its own `term_definition` card.
- `basic`: front = question, back = answer
- `cloze`: front = sentence with blank, back = missing term

## Distractor / Quality Rubric

- Front should be concise (under 120 characters when possible).
- Back must be accurate and grounded in evidence segments.
- Difficulty: `easy` for direct recall, `medium` for applied recall, `hard` for synthesis.

## Coverage

- Generate flashcards for the most memorable, high-value concepts in the batch —
  prioritize `essential` then `supporting` concepts. Do **not** force one card per
  concept; skip thin or redundant concepts.
- When an item budget is provided for the batch, stay within it and choose the
  number by how much memorable material the batch genuinely supports.
- Never emit two cards for the same term or the same list; one card per entry.

## Draft Checklist

1. One card per worthwhile concept (term_definition preferred for terms), within
   the requested budget.
2. Cite wiki_ids_cited and source_chunk_ids.
3. Include difficulty and optional tags.

## Critique Checklist

1. Is the back grounded in evidence, not hallucinated?
2. Does the front use the canonical label?
3. Is difficulty calibrated correctly?
4. Are citations valid for the batch?

## Output Schema

```json
{
  "items": [
    {
      "item_id": "uuid",
      "type": "flashcard",
      "subtype": "term_definition",
      "difficulty": "easy|medium|hard",
      "wiki_ids_cited": ["wiki-id"],
      "source_chunk_ids": ["segment-id"],
      "tags": ["tag"],
      "front": "term or prompt",
      "back": "answer or definition"
    }
  ]
}
```
