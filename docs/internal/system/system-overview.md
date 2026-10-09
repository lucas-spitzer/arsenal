# Arsenal system map

This file is the source of truth for how Arsenal is organized: names, surfaces, Foundry systems, output kinds, and who reads what. Stage inventories live next to the code ([`api/app/pipeline.py`](../../../api/app/pipeline.py), [`api/README.md`](../../../api/README.md)). Mathesys file contracts live in [`artifacts-catalog.md`](./artifacts-catalog.md).

Current behavior wins. The one-line direction: Arsenal stays a private educational environment, not a public SaaS.

## Names

| Name | Role |
|------|------|
| **Arsenal** | Umbrella: one SPA, one API, one repo |
| **Foundry** | Production studio. Produces wiki entries, artifacts, and assessments |
| **Academy** | Learning surface. Curates wiki, artifacts, and assessments in **Library** |
| **Intellex** | Ingest, structured source, research, and Wiki Knowledge. Never called Library |
| **Mathesys** | File artifacts from the structured source (and, for study sheets, the original file) |
| **QnGen** | Assessments from canonical wiki + evidence segments |

**Library** is Academy’s catalog of every workspace output (artifacts, wiki entries, flashcards, quizzes, scenarios). Intellex is not the library.

Foundry produces. Academy curates. Wiki has the in-product write path (edit, deprecate, rewrite). New files and new assessment rows still come from Foundry production runs.

## Three Foundry systems, three output kinds

Do not stuff wiki into Mathesys, or flashcards into the artifact catalog.

| Kind | Owner | What it is | Where it starts |
|------|--------|------------|--------------------|
| **Wiki entries** | Intellex | Canonical `wiki_entries` (live knowledge). `wiki_json` is only a Mathesys snapshot of that work | Knowledge project, Run 1 |
| **Artifacts** | Mathesys | Stored files | OPS: `electronic_book`, `narration_audio`, `wiki_json`. Design: `study_material` |
| **Assessments** | QnGen | Rows: flashcards, quizzes, scenarios | Knowledge project, Run 2 |

`web_explainer` is catalogued as a future Mathesys type. It is not a live `target_artifact`.

## Intellex knowledge (two objects)

Intellex is a knowledge base in two senses. Keep them distinct.

1. **Structured source** — ingest writes `document_chapters`, `ndr_segments`, and research/enrichment. Mathesys ebook and narration read this. Study sheets read the original source file.
2. **Canonical wiki** — A knowledge project in Forge Knowledge uploads notes (or pasted text) against an already ingested book. Run 1 is `transcribe-wiki-notes` then `structure-wiki-notes`. The batch attachment is the notes file. The batch `source_id` is the book, so evidence still lands on that book's segments. Academy edits the resulting entries.

Knowledge is not extracted as a leftover Intellex ingest stage. Ingest does not promote wiki entries. OPS New Run does not offer Wiki Knowledge or assessment targets. Those stages still exist for a knowledge project's own production runs.

## Production run

A **production run** is one work order: selected sources plus `target_artifacts`. One table, one OPS timeline.

- Upload enqueues an **ingest-only** run (`target_artifacts` empty). Intellex base: store → parse → normalize → trim → structure → validate → chunk → source-research. Later runs reuse ingest when the source is already processed. `web-enrichment` runs only when `electronic_book` is a target, immediately before `create-ebook`.
- OPS New Run targets are ebook, narration, and wiki export. A knowledge project uses its own runs: `knowledge_structure` (transcribe and structure), `knowledge_draft` (the assessment stages that were turned on, then `attach-visuals`), and `knowledge_visuals` (attach only, when an image changes later).
- Study material stays a Design-tab run with its own pipeline. It is not a `target_artifact`.

## Loop (as shipped)

1. Upload a source in Foundry → ingest-only production run.
2. New Run: pick sources and ebook, narration, or wiki export.
3. Forge Knowledge, Study material: configure a sheet from the original file, then generate.
4. Forge Knowledge, Knowledge: upload notes against an ingested book. Run 1 writes wiki entries. Compose turns flashcards on per entry and questions or scenarios on for the project, and can attach a flashcard image. Run 2 drafts only those items and attaches uploaded files. A later image change is an attach-only run.
5. Academy Library is where artifacts, wiki entries, and assessments are found, opened, and (for wiki) edited. Flashcard, question, and scenario images render from placement. The reader and the wiki editor stay text.

## Direction

Stay private and operator-driven. Foundry remains a browser production studio, not a pile of scripts. Academy remains where the package is used and the wiki is kept honest.
