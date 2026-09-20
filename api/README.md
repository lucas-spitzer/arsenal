# Arsenal API

FastAPI service for Arsenal backend authorization, workspaces, sources, stages, and production-run orchestration.

## Local Setup

Create a virtual environment and install dependencies:

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `api/.env` from `.env.example` and fill in the real values:

```bash
cp .env.example .env
```

Required secrets (the app or worker will fail without these for a full pipeline run):

```text
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY (or legacy SUPABASE_ANON_KEY)
SUPABASE_SERVICE_ROLE_KEY
OPENAI_API_KEY
ANTHROPIC_API_KEY
GEMINI_API_KEY (optional; required only if a stage uses Gemini, including Gemini TTS)
CARTESIA_API_KEY (optional; required only if a stage uses Cartesia Sonic TTS)
LLAMAPARSE_API_KEY
```

Infrastructure variables have defaults (see `.env.example`).

### Environment variables by pipeline step

| Pipeline step | Variables | Notes |
|---|---|---|
| All | `SUPABASE_*`, `REDIS_URL`, `FRONTEND_ORIGINS`, `SOURCES_BUCKET`, `RQ_QUEUE_NAME` | Core API + worker |
| `parse` | `LLAMAPARSE_API_KEY`, `LLAMAPARSE_TIER` | LlamaParse PDF parsing |
| `source-research` | `OPENAI_API_KEY`, `SOURCE_RESEARCH_MODEL`, `SOURCE_RESEARCH_MAX_CHARS` | OpenAI JSON extraction |
| `extract-knowledge` | `ANTHROPIC_API_KEY`, `LLM_EXTRACT_KNOWLEDGE_PROVIDER`, `LLM_EXTRACT_KNOWLEDGE_MODEL`, `EXTRACT_MAX_ENTRIES_PER_{CHAPTER,DOCUMENT}`, `EXTRACT_MIN_{CONFIDENCE,SELECTION_SCORE}`, `EXTRACT_{ESSENTIAL,SUPPORTING}_FRACTION`, `EXTRACT_EMBEDDING_DEDUP`, `EXTRACT_EMBEDDING_{MODEL,SIMILARITY_THRESHOLD}` | LLM factory action + wiki-entry selection bands (0 = no cap/gate) + comparative importance fractions + optional embedding dedup |
| `generate-flashcards` / `generate-questions` / `generate-scenarios` | `DRAFT_MODEL`, `CRITIQUE_MODEL`, `LLM_QNGEN_{DRAFT,CRITIQUE}_PROVIDER`, `CONCEPT_BATCH_SIZE`, `QNGEN_MAX_REPAIR_TURNS`, `QNGEN_FLASHCARDS_PER_CHAPTER_{MIN,MAX}`, `QNGEN_SCENARIOS_PER_CHAPTER_{MIN,MAX}` | Blueprint-driven generation (per-chapter count bands) + draft + critique + grounding-repair passes |
| `create-ebook` | — | Deterministic EPUB build |
| `generate-narration` | `SPEECHIFY_API_KEY`, `ELEVENLABS_API_KEY`, `CARTESIA_API_KEY`, and/or `GEMINI_API_KEY`; `AUDIO_NARRATION_MODEL`, `AUDIO_NARRATION_VOICE_ID` | Default TTS is Speechify (`simba-3.2` / `hugh_32`). Model prefix selects the provider: `eleven*` → ElevenLabs, `sonic*` → Cartesia, `gemini*` → Gemini TTS. |

Each LLM action has a dedicated model env var (`SOURCE_RESEARCH_MODEL`, `SOURCE_WEB_ENRICHMENT_MODEL`, `WIKI_STRUCTURING_MODEL`, `WIKI_REVISE_MODEL`, `DRAFT_MODEL`, `CRITIQUE_MODEL`, `READER_DEFINE_MODEL`, `STUDY_SHEET_MODEL`). Optional `LLM_<ACTION>_PROVIDER` overrides the registry provider. Defaults and supported actions live in [`app/llm_actions.py`](app/llm_actions.py).

`SUPABASE_ANON_KEY` may be used instead of `SUPABASE_PUBLISHABLE_KEY` for older Supabase projects.

Never put `SUPABASE_SERVICE_ROLE_KEY` in the Vite frontend.

Apply the Supabase migrations in `supabase/migrations/` in order before using the ingest endpoints (see [`supabase/README.md`](../supabase/README.md)).

## Run API

```bash
cd api
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

## Run Redis + Worker

Foundry uses Redis for the RQ job queue. Use **either** Docker or Homebrew.

### Option A — Docker (recommended if you use Docker Desktop)

From the repository root:

```bash
docker compose up -d redis
docker compose ps
```

Redis will be available at `redis://localhost:6379/0`.

Stop it later with:

```bash
docker compose down
```

### Option B — Homebrew Redis

```bash
brew install redis
brew services start redis
redis-cli ping   # should print PONG
```

### Start the worker

In a second terminal:

```bash
cd api
source .venv/bin/activate
python run_worker.py
```

The frontend should use:

```bash
VITE_API_BASE_URL="http://localhost:8000"
```

## Endpoints

All endpoints below except `/health` require:

```text
Authorization: Bearer <supabase-access-token>
```

### Health / auth

```text
GET /health
GET /me
```

### Workspaces

```text
GET    /workspaces
POST   /workspaces
GET    /workspaces/{workspace_id}
PATCH  /workspaces/{workspace_id}
DELETE /workspaces/{workspace_id}
```

### Sources

```text
GET    /workspaces/{workspace_id}/sources
POST   /workspaces/{workspace_id}/sources
GET    /workspaces/{workspace_id}/sources/{source_id}
GET    /workspaces/{workspace_id}/sources/{source_id}/segments
DELETE /workspaces/{workspace_id}/sources/{source_id}
```

`POST /sources` accepts `multipart/form-data` with a `file` field. Each successful upload automatically queues an ingest-only production run (Intellex base pipeline through `web-enrichment`; wiki entries are not extracted here). Redis and the RQ worker must be running.

### Stages

```text
GET /stages
GET /stages/{stage_id}/{version}
```

Stage `version` values use major.minor format only (e.g. `1.0`, `2.0`).

Optional query param: `?module=intellex|mathesys|qngen`

### Wiki

```text
GET    /workspaces/{workspace_id}/wiki/entries
POST   /workspaces/{workspace_id}/wiki/entries
GET    /workspaces/{workspace_id}/wiki/entries/{wiki_entry_id}
PATCH  /workspaces/{workspace_id}/wiki/entries/{wiki_entry_id}
DELETE /workspaces/{workspace_id}/wiki/entries/{wiki_entry_id}
POST   /workspaces/{workspace_id}/wiki/entries/{wiki_entry_id}/revise
GET    /workspaces/{workspace_id}/wiki/disputes
POST   /workspaces/{workspace_id}/wiki/ingest-batches
POST   /workspaces/{workspace_id}/wiki/ingest-batches/from-files
GET    /workspaces/{workspace_id}/wiki/ingest-batches
GET    /workspaces/{workspace_id}/wiki/ingest-batches/{batch_id}
```

Optional query params on entries: `?status=canonical|disputed|open`, `?search=term`

`POST …/revise` returns a proposed definition (and optional label/aliases). It does not write the row; save with `PATCH`. Wiki Knowledge on New Run uses each selected source file as the notes. Markdown is a passthrough; PDFs go through LlamaParse. Ingest-batch endpoints remain for API clients.

### Assessments (QnGen)

```text
GET /workspaces/{workspace_id}/flashcards
GET /flashcards/{flashcard_id}
GET /workspaces/{workspace_id}/quizzes
GET /quizzes/{quiz_id}
GET /workspaces/{workspace_id}/scenarios
GET /scenarios/{scenario_id}
```

### Artifacts

```text
GET /workspaces/{workspace_id}/artifacts
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/download
```

`GET /download` returns a short-lived signed URL for the EPUB file.

### Production runs

```text
GET  /workspaces/{workspace_id}/production-runs
POST /workspaces/{workspace_id}/production-runs
GET  /production-runs/{production_run_id}
GET  /production-runs/{production_run_id}/stage-runs
GET  /stage-runs/{stage_run_id}
```

Example production run body:

```json
{
  "source_ids": ["uuid"],
  "target_artifacts": ["electronic_book", "flashcards", "quizzes", "scenarios"]
}
```

`target_artifacts` is optional. An empty list runs Intellex ingest only.

Supported `target_artifacts` values:

- `electronic_book` — Mathesys create-ebook (chapter-based EPUB per source)
- `narration_audio` — Mathesys generate-narration (timed clips + manifest per source)
- `wiki_json` — Mathesys export-wiki-json (curated wiki snapshot per source)
- `wiki_knowledge` — Intellex transcribe-wiki-notes + structure-wiki-notes (canonical wiki entries from each selected source file)
- `study_sheet` — Mathesys generate-study-sheet (one- or two-page PDF from the source file)
- `flashcards` — QnGen generate-flashcards
- `quizzes` — QnGen generate-questions
- `scenarios` — QnGen generate-scenarios

The PDF lands at `{workspace_slug}/{source_slug}/sheet.pdf`. Markdown sources skip Intellex ingest and still generate a sheet from the original file.

Full pipeline worker behavior:

- always completes Intellex ingest (`store`, `parse`, `normalize-document`, `trim-document-boundaries`, `structure-document`, `validate-structure`, `chunk`, `source-research`, `web-enrichment`); reuses prior ingest/Intellex results when a source was already processed; skips Intellex for markdown sources (study sheets still generate from the original file)
- when `wiki_knowledge` is a target, inserts one ingest batch per source (attachments point at the existing source object), then runs `transcribe-wiki-notes` (markdown passthrough; skipped when notes are already filled or there are no files) then `structure-wiki-notes` (writes canonical wiki entries)
- optionally runs Mathesys stages and QnGen stages based on `target_artifacts`
- promotes artifacts and assessment entities
- marks production run `completed` when finished

## Tests

```bash
cd api
source .venv/bin/activate
pip install pymupdf
python -m pytest tests/
```
