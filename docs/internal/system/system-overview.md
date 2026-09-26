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

| Kind | Owner | What it is | Live targets today |
|------|--------|------------|--------------------|
| **Wiki entries** | Intellex | Canonical `wiki_entries` (live knowledge). `wiki_json` is only a Mathesys snapshot of that work | `wiki_knowledge` |
| **Artifacts** | Mathesys | Stored files | `electronic_book`, `narration_audio`, `wiki_json`, `study_material` (Design tab, not a `target_artifact`) |
| **Assessments** | QnGen | Rows: flashcards, quizzes, scenarios | `flashcards`, `quizzes`, `scenarios` |

`web_explainer` is catalogued as a future Mathesys type. It is not a live `target_artifact`.

## Intellex knowledge (two objects)

Intellex is a knowledge base in two senses. Keep them distinct.

1. **Structured source** — ingest writes `document_chapters`, `ndr_segments`, and research/enrichment. Mathesys ebook and narration read this. Study sheets read the original source file.
2. **Canonical wiki** — Wiki Knowledge treats each selected source file as notes (`transcribe-wiki-notes` → `structure-wiki-notes`) and writes `wiki_entries`. QnGen reads canonical entries plus evidence segments. Academy edits that set.

Knowledge is not extracted as a leftover Intellex ingest stage. Ingest does not promote wiki entries.

## Production run

A **production run** is one work order: selected sources plus `target_artifacts`. One table, one OPS timeline.

- Upload enqueues an **ingest-only** run (`target_artifacts` empty). Intellex base: store → parse → normalize → trim → structure → validate → chunk → source-research → web-enrichment. Later runs reuse ingest when the source is already processed.
- `wiki_knowledge` is an **Intellex** target on the same run, not a Mathesys artifact. It runs after ingest so QnGen in the same run can use the new entries.
- Other targets append Mathesys and/or QnGen steps.

## Loop (as shipped)

1. Upload a source in Foundry → ingest-only production run.
2. New Run: pick sources and targets.
3. Intellex wiki target (optional) writes canonical entries.
4. Mathesys (optional) packages the structured source — or the original file, for study sheets.
5. QnGen (optional) builds assessments from curated wiki.
6. Academy Library is where those three kinds are found, opened, and (for wiki) edited.

## Direction

Stay private and operator-driven. Foundry remains a browser production studio, not a pile of scripts. Academy remains where the package is used and the wiki is kept honest.
