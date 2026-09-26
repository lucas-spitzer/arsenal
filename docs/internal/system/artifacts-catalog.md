# Arsenal Artifact Catalog

This is a living document that defines each available artifact in Arsenal: what it is for, how it is packaged, which model produces it, and how Academy is expected to use it. Update it when a type is added, retired, or its contract changes. Implementation details live in code; this file is the product contract.

Arsenal currently treats five Mathesys outputs as first-class artifacts. QnGen assessments (flashcards, quizzes, scenarios) are related production outputs, not entries in this catalog.

Identifiers use `snake_case` to match `artifact_type` in the API and database.

---

## Catalog

| Artifact | Identifier | Format | Default model | Academy role |
|---|---|---|---|---|
| Electronic Book | `electronic_book` | Single EPUB | GPT-5 nano | Read the curated source as a simple book |
| Audio Narration | `narration_audio` | Sequential audio clips + manifest | Gemini 3.8 Flash TTS | Listen, and voice over other artifacts |
| Wiki Export | `wiki_json` | Single JSON document | None (deterministic snapshot) | Portable curated knowledge for a source |
| Web Explainer | `web_explainer` | HTML + CSS + JS | Claude Opus 5.5 | Answer one question with interactive visuals |
| Study Material | `study_material` | Printable one-page PDF (US Letter) | GPT-6 Sol (diagrams and text), GPT Image 2.5 Flare (images), GPT-6 Sol (layout) | Print a templated, themed reference sheet or cut-out cards |

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
- **Model:** Gemini 3.8 Flash TTS (default, Sadaltager). Simba 3.2, ElevenLabs v3, Cartesia Sonic 3.6, and Gemini 3.8 Flash-Lite TTS are selectable alternatives.
- **Academy use:** Listen on its own, or play as a voiceover while another artifact is on screen (book, explainer, and later types).

Today the pipeline synthesizes one clip per chapter (splitting a chapter only when joined paragraph text exceeds the TTS character cap), stores word-level timings on each paragraph row, and publishes a JSON manifest as the downloadable artifact. Paragraphs in the same clip share `audio_path`; timings are seconds on that clip so the Reader can seek and highlight. Speechify and ElevenLabs clips are MP3. Cartesia and Gemini clips are WAV. Cartesia returns PCM, which the worker wraps. Gemini 3.8 returns WAV.

Word timings land on the same `words` array in `narration_segments` and the published manifest, with source character spans and alignment-quality metadata. ElevenLabs returns per-character alignment that maps directly to source tokens. Speechify returns speech marks with source character offsets and millisecond timestamps; the client maps overlapping marks instead of assuming provider and display tokens have the same indexes. Cartesia SSE returns word timestamps in seconds, requests original-text timestamps, and uses ordered text alignment when token boundaries differ. Gemini TTS does not return alignments, so the worker uses forced alignment when ElevenLabs alignment is configured. Without it, Gemini remains explicitly estimated and the Reader uses sentence-level progress rather than claiming exact word sync. A paragraph longer than the provider cap is skipped rather than truncated.

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
- **Model:** Claude Opus 5.5
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
- **Model pin.** The selectable catalog model is `claude-opus-5-5`. Pin that id when the stage is built.

---

## Study Material

- **Identifier:** `study_material`
- **Definition:** A printable page built from a predefined template, a predefined theme, and generated Text, Diagram, and Image components. Replaces the retired Study Sheet.
- **Format:** One-page PDF (US Letter) plus the finalized HTML it was printed from.
- **Model:** Diagrams and text share the workspace-configurable `study_material` action (default GPT 6 Sol). Layout uses `study_material_orchestrator` (default GPT 6 Sol). Images default to OpenAI `gpt-image-2.5-flare`; each image component can switch to Google `gemini-3.1-flash-image` or either provider's premium model.
- **Academy use:** Download and print from the Library's Study Material group. Not source-bound.

### Design intent

Template defines where content can exist. Theme defines how it looks. Components define what exists. The orchestrator arranges components inside their sections; code enforces geometry, constraints, versioning, rendering, and export.

Built in the Foundry **Design** tab (DSN): title, theme, and template first, then components per template section, then generation. Diagrams and images generate before text so text is written around them. The model describes diagrams as nodes and connections only; code lays them out and renders SVG. The orchestrator plans order, size, spacing, and emphasis per section, then a Chromium fit loop tightens visual sizes and text density until nothing is clipped. Finalize re-checks page size, clipping, image resolution (150 DPI minimum), fonts, and assets, prints with headless Chromium, and adds the PDF to the Library.

Themes (`usmc`, `field-manual`) and templates (`branded-sheet`, `branded-sheet-split`, `index-card-cutout`) are JSON files in `api/app/mathesys/study_material/catalog/`. The USMC theme follows the Marines.mil style guide, ships the Eagle, Globe, and Anchor and MARINES wordmark (the author chooses whether to lock one into the logo band), and always prints the disclaimer “Unofficial knowledge for educational use; not endorsed by the USMC or DoD.” in the footer, or on every card for Index Card Cutout.

Every generated component keeps a version row (output, instructions, model, settings, theme, reference files, time). Phase 2 adds regeneration with side-by-side comparison and section re-layout instructions.

---

## Related outputs (not in this catalog)

These are produced by Foundry and stored as assessment rows, but they are not artifacts in the sense above:

| Output | Identifier | Role |
|---|---|---|
| Flashcards | `flashcards` | QnGen retrieval drill |
| Quizzes | `quizzes` | QnGen question set |
| Scenarios | `scenarios` | QnGen applied scenario set |

If one of these later needs the same product-contract treatment as the types above, promote it into this catalog rather than documenting it only in pipeline READMEs.
