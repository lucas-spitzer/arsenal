# Arsenal Artifact Catalog

This is a living document that defines each available artifact in Arsenal: what it is for, how it is packaged, which model produces it, and how Academy is expected to use it. Update it when a type is added, retired, or its contract changes. Implementation details live in code; this file is the product contract.

Arsenal currently treats five Mathesys outputs as first-class artifacts. QnGen assessments (flashcards, quizzes, scenarios) are related production outputs, not entries in this catalog.

Identifiers use `snake_case` to match `artifact_type` in the API and database.

---

## Catalog

| Artifact | Identifier | Format | Default model | Academy role |
|---|---|---|---|---|
| Electronic Book | `electronic_book` | Single EPUB | GPT-5 nano | Read the curated source as a simple book |
| Audio Narration | `narration_audio` | Sequential audio clips + manifest | Simba 3.2 | Listen, and voice over other artifacts |
| Wiki Export | `wiki_json` | Single JSON document | None (deterministic snapshot) | Portable curated knowledge for a source |
| Web Explainer | `web_explainer` | HTML + CSS + JS | Claude Opus 5 | Answer one question with interactive visuals |
| Study Sheet | `study_sheet` | Printable PDF (one or two pages) | Gemini 3.7 Flash | Memorize a subject from a double-sided sheet |

---

## Electronic Book

- **Identifier:** `electronic_book`
- **Definition:** A curated book that contains only the most relevant text, excluding portions such as the preface, table of contents, glossary, footers, and more.
- **Format:** A single EPUB file that emulates a simple book.
- **Model:** GPT-5 nano
- **Academy use:** Primary reading surface. The learner works through the source as a chaptered book.

Intellex already strips non-learning material and persists a chapter/section model. Mathesys then packages that structured book as one EPUB per source (`format: epub3`). The EPUB is the portable reading object; Academy’s reader is the in-product surface.

The create-ebook step itself is currently a deterministic render of the structured book, not a free-form LLM rewrite. GPT-5 nano is the intended model for any authoring or cleanup that still happens on the path into that EPUB.

---

## Audio Narration

- **Identifier:** `narration_audio`
- **Definition:** An audiovisual narration designed to be used in Academy as a voiceover for other educational artifacts.
- **Format:** A set of sequential audio clips that combine to form a complete transcription.
- **Model:** Simba 3.2 (Speechify; ElevenLabs remains an alternative)
- **Academy use:** Listen on its own, or play as a voiceover while another artifact is on screen (book, explainer, and later types).

Today the pipeline synthesizes one MP3 per chapter (splitting a chapter only when joined paragraph text exceeds the TTS character cap), stores word-level timings on each paragraph row, and publishes a JSON manifest as the downloadable artifact. Paragraphs in the same clip share `audio_path`; timings are seconds on that clip so the Reader can seek and highlight. Clips are audio-only (MP3), not MP4 video.

Word timings come from the TTS provider and land on the same `words` array in `narration_segments` and the published manifest. ElevenLabs returns per-character alignment that we group into words. Speechify returns speech marks (word-level `start_time` / `end_time` in milliseconds) from `POST /v1/audio/speech` and `POST /v1/audio/stream/with-timestamps`; the client converts those to seconds so the Reader contract is identical. A paragraph longer than the provider cap is skipped rather than truncated.

The important product rule is composition, not container: narration is a timed voice track aligned to source text, reusable as a voiceover rather than a standalone “audiobook dump.”

---

## Wiki Export

- **Identifier:** `wiki_json`
- **Definition:** A versioned JSON snapshot of the curated wiki for a source: canonical entries the author kept while reading, packaged as a downloadable knowledge artifact.
- **Format:** A single JSON file (`format: json`) that can be downloaded, diffed, or re-imported.
- **Model:** None. Curation happens via Wiki Knowledge on a New Run (`wiki_knowledge` production runs) and Academy Library entry management; `export-wiki-json` is a deterministic Mathesys snapshot of that work.
- **Academy use:** Interchange and review, not a primary reading surface. The live wiki remains the in-product knowledge base; this artifact is the portable copy.

The export includes canonical entries that cite the source (or record it in origin) plus workspace-level entries with no source affiliation, so curated knowledge is not silently dropped. Entries tied only to other sources are excluded. The document records export version, source identity, entry counts by kind and scope, and standalone entry payloads (labels rather than internal ids for prerequisites).

Production requires canonical wiki entries for the source. An empty wiki is not a valid Wiki Export.

---

## Web Explainer

- **Identifier:** `web_explainer`
- **Definition:** A concise webpage explainer that visually answers one question with interactive animations and text that can be read aloud as audio.
- **Format:** HTML for structure, CSS for style, and JS for animation and interaction.
- **Model:** Claude Opus 5
- **Academy use:** Short, focused visual lesson. One question in, one explainer out. Text on the page is narratable.

### Design intent

A web explainer is not a lesson site, a chapter rewrite, or a mini-app. It is a single visual answer: setup, motion that shows the idea, and short accompanying text. If the learner cannot state the question the page answers, the artifact is too broad.

The three-file split (HTML / CSS / JS) is the generation contract. Packaging for storage and Academy playback can still be a small bundle (for example a directory or zip) as long as the parts stay separable for review and repair.

### Open questions

- **Prompt input.** Who names the one question — the operator, a wiki concept, a chapter heading, or an automatic pass over the source?
- **Cardinality.** One explainer per source, per chapter, or an operator-selected set?
- **Audio.** Is read-aloud generated with the explainer, reused from `narration_audio`, or synthesized at view time from the on-page text?
- **Safety.** Generated JS must run in Academy inside a sandbox (no parent DOM, no network, no storage). Treat the bundle as untrusted.
- **Motion.** Honor reduced-motion preferences; animation should explain, not decorate.
- **Visual system.** Learner-facing explainers may need a pedagogical visual language related to, but not identical to, the Foundry console style guide.
- **Model pin.** Catalog today has Claude Opus 4.8, not Opus 5. Record the intended tier here; pin the exact model id when the stage is built.

---

## Study Sheet

- **Identifier:** `study_sheet`
- **Definition:** A printable double-sided document (two pages) that contains key study material for a specified subject to be memorized.
- **Format:** PDF (US Letter, duplex on the long edge).
- **Model:** Gemini 3.7 Flash
- **Academy use:** Download and print. Do not open the Reader.

### Design intent

A study sheet is a physical memory object. The hard constraint is the point: two sides, one sheet, dense but readable, meant to be studied until the page is unnecessary. It complements flashcards (prompt/response drill) rather than replacing them. Flashcards test retrieval; the sheet is the map of what is worth retrieving.

This artifact is a **Mathesys production-run stage** (`generate-study-sheet`). Select Study Sheet on a new production run. Gemini reads the library source file (PDF or markdown) and writes body HTML; Foundry wraps it in owned print chrome (letter page, margins, scarlet headings, gold rules) and prints to PDF. If the print is more than two pages, the model is asked to cut material (up to three attempts) and the stage fails if it still overflows. One page is allowed. Facts must come from the file; the model may recreate a source diagram as simple SVG but must not invent mnemonics or examples.

The operator curates the input by choosing the source. A field-manual PDF that cannot compress onto two pages fails on purpose. Do not treat a list-heavy notes file as the only valid shape: prose, tables, and mixed sources must use the same block types.

Canonical print size is US Letter, duplex on the long edge, with margins that survive home printers. DOCX is out of scope.

---

## Related outputs (not in this catalog)

These are produced by Foundry and stored as assessment rows, but they are not artifacts in the sense above:

| Output | Identifier | Role |
|---|---|---|
| Flashcards | `flashcards` | QnGen retrieval drill |
| Quizzes | `quizzes` | QnGen question set |
| Scenarios | `scenarios` | QnGen applied scenario set |

If one of these later needs the same product-contract treatment as the types above, promote it into this catalog rather than documenting it only in pipeline READMEs.
