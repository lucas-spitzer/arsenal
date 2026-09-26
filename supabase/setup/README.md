# Foundry Supabase Setup

Use the numbered scripts (`01`–`04`) to bootstrap a **fresh** Supabase project. They contain the full current schema and stage seeds.

Operator patches (`alter-*.sql`, `restore-stages.sql`) are for **existing** databases only — do not include them in the greenfield loop.

## Prerequisites

- A Supabase project with **Google OAuth** configured in Auth (required for sign-in).
- The FastAPI backend uses the **service role** key for data access in V1. Client roles are revoked from application tables.

## Apply setup (fresh project)

Run the SQL files **in order** in the Supabase SQL editor (or pipe them through `psql`):

```text
supabase/setup/01-auth-and-extensions.sql
supabase/setup/02-schema.sql
supabase/setup/03-seed-stages.sql
supabase/setup/04-storage-and-rls.sql
```

Example with the Supabase CLI linked to your project:

```bash
for f in \
  supabase/setup/01-auth-and-extensions.sql \
  supabase/setup/02-schema.sql \
  supabase/setup/03-seed-stages.sql \
  supabase/setup/04-storage-and-rls.sql
do
  supabase db execute --file "$f"
done
```

Do **not** glob `supabase/setup/*.sql` — that would also pick up operator patches.

After running setup, replace the placeholder owner email in `approved_users` with your own Google account address.

## Existing database patches

Run these only on databases that already have a Foundry schema and need a targeted upgrade. Fresh installs from `01`–`04` already include the current shape.

| File | When to run |
|------|-------------|
| `../maintenance/alter-study-material.sql` | DB was created before Study Material. Adds `production_runs.label`, the `study_materials` / `study_material_components` / `study_material_component_versions` tables with RLS + revokes, swaps `study_sheet` for `study_material` in `artifacts_type_check`, widens the `sources` bucket MIME list (text, CSV, HTML, PNG, JPEG, WebP), and seeds the four Study Material stages. Idempotent. |
| `alter-library-slugs.sql` | DB was created before frozen workspace/source slugs. Adds `workspaces.slug`, unique workspace names, and `sources.slug`. |
| `alter-wiki-knowledge-pipeline.sql` | DB was created before wiki ingest as a production-run target. Adds `wiki_ingest_batches.production_run_id`. Re-run `03-seed-stages.sql` for the new wiki stages. |
| `alter-stage-settings-tts.sql` | DB was created before Speechify narration settings. Widens `workspace_stage_settings.provider` to include `speechify` / `elevenlabs` and adds nullable `voice_id`. |
| `alter-stage-settings-providers.sql` | DB was created before Google and Cartesia stage settings. Widens `workspace_stage_settings.provider` to include `google` / `cartesia`. |
| `alter-sources-bucket-wav.sql` | DB was created before Cartesia/Gemini WAV clips. Adds `audio/wav` to the `sources` bucket allowlist. |
| `alter-drop-artifacts-bucket.sql` | Operator note only (SQL no-op). Supabase blocks dropping `storage.buckets` / `storage.objects` from SQL. After migrating objects into the `sources` bucket, purge the legacy `artifacts` bucket via the Storage API or Dashboard. |
| `alter-discussion-threads.sql` | DB was created before persisted discussion threads. Adds `discussion_threads` and `discussion_messages` with RLS + role revokes. Idempotent. |
| `restore-stages.sql` | Short pointer: re-run `03-seed-stages.sql` to repair a wiped or stale `stages` table. |
| `../maintenance/delete-production-run.sql` | Operator utility. Deletes one production run and the rows it created. Storage files cannot be deleted from SQL. |
| `../maintenance/delete-source.sql` | Operator utility. Deletes one source and the rows it created. Storage files cannot be deleted from SQL. |

### Delete a production run

`production_runs` children use `ON DELETE SET NULL`, so deleting the run row leaves assessments, artifacts, wiki batches, and stage runs behind. Use this instead.

1. Open `supabase/maintenance/delete-production-run.sql`.
2. Set `target_run_id`.
3. Leave `dry_run true` and run it. That run errors on purpose and lists what would be removed.
4. Set `dry_run false` and run it again. Success in the SQL editor only means the delete ran if `dry_run` is false.

The script does not delete source rows or original uploads. Intellex segments, chapters, and `work/` files stay unless `purge_ingest` is true, and then only for sources no other production run still lists. Tables that exist in `02-schema.sql` but not on the live database are skipped.

Supabase forbids `DELETE` on `storage.objects` from SQL. After a successful row delete, leftover keys appear in notices and in `pg_temp.purge_storage_paths`. Remove those files from the `sources` bucket in Dashboard → Storage, or with the Storage API.

If the run is still queued or running, stop the worker job first.

```bash
supabase db execute --file supabase/maintenance/delete-production-run.sql
```

### Delete a source

Most source children use `ON DELETE SET NULL`, so deleting the source row leaves assessments, artifacts, wiki batches, disputes, and discussion threads behind. Use this instead.

1. Open `supabase/maintenance/delete-source.sql`.
2. Set `target_source_id`.
3. Leave `dry_run true` and run it. That run errors on purpose and lists what would be removed.
4. Set `dry_run false` and run it again.

Tables that exist in `02-schema.sql` but not on the live database (for example `assessment_sets`) are skipped. `ndr_segments`, `document_chapters`, and `narration_segments` cascade with the source. Wiki entries owned only by this source are deleted; shared entries drop this source from `evidence`. Production runs keep their other sources; this script only removes the id from `source_ids`.

Supabase forbids `DELETE` on `storage.objects` from SQL. After a successful row delete, leftover keys appear in notices and in `pg_temp.purge_storage_paths`. Remove those files from the `sources` bucket in Dashboard → Storage, or with the Storage API.

```bash
supabase db execute --file supabase/maintenance/delete-source.sql
```

### Wiki file-ingest columns

```bash
supabase db execute --file supabase/setup/alter-wiki-ingest-file-ingest.sql
```

### Study Material

```bash
supabase db execute --file supabase/maintenance/alter-study-material.sql
```

The artifact type swap fails if any `study_sheet` artifact rows remain; delete them first.

### Wiki knowledge production-run column

```bash
supabase db execute --file supabase/setup/alter-wiki-knowledge-pipeline.sql
supabase db execute --file supabase/setup/03-seed-stages.sql
```

### Stage settings TTS providers and voice_id

```bash
supabase db execute --file supabase/setup/alter-stage-settings-tts.sql
```

### Stage settings Google and Cartesia providers

```bash
supabase db execute --file supabase/setup/alter-stage-settings-providers.sql
```

### Sources bucket WAV clips

```bash
supabase db execute --file supabase/setup/alter-sources-bucket-wav.sql
```

### Legacy `artifacts` storage bucket

1. Migrate objects: `cd api && python -m scripts.migrate_artifacts_into_sources`
2. Confirm downloads work.
3. Empty and delete the bucket: `python -m scripts.migrate_artifacts_into_sources --purge-legacy-bucket`  
   Or Dashboard: Storage → `artifacts` → Empty bucket → Delete bucket.

`alter-drop-artifacts-bucket.sql` is safe to open in the SQL editor but does not delete the bucket.

### Nest colocated artifacts by type

Rows already under `sources/.../artifacts/{artifact_id}/` (no type folder) can be copied into `artifacts/{ebook|narration|wiki}/{artifact_id}/`:

```bash
cd api && python -m scripts.nest_artifacts_by_type --dry-run
cd api && python -m scripts.nest_artifacts_by_type
```

Old objects are left in place. Voice-id folders under `artifacts/` (working MP3 dumps) are skipped.

### Publish missing narration artifacts

`generate-narration` runs that fail mid-TTS still write per-segment MP3s. To create the missing `narration_audio` artifacts row from those clips:

```bash
cd api && python -m scripts.publish_narration_artifacts --dry-run
cd api && python -m scripts.publish_narration_artifacts
```

## What gets created

### Auth and extensions

- `approved_users` — internal authorization allowlist
- Extensions: `citext`, `pgcrypto`, `vector` (in `extensions` schema)
- Trigger helper: `set_updated_at()`
- RAG helpers: `match_ndr_segments`, `match_wiki_entries` (service role only)

### Core tables

- `workspaces`, `sources`, `production_runs`, `stage_runs`, `stages`
- `workspace_stage_settings` — per-workspace LLM and narration provider/model/voice overrides
- API cost tracking columns on `stage_runs` and `production_runs`

### Intellex content

- `ndr_segments` — chunked parsed text with page locators, optional `md`, and embeddings
- `document_chapters` — persisted chapter/section segmentation (`sections` jsonb)
- `wiki_entries` — canonical terms, concepts, and insights (`entry_kind`; optional `candidate` status)
- `wiki_disputes` — non-blocking conflict log
- `wiki_ingest_batches` — one row per source on a `wiki_knowledge` production run; attachments point at the existing source file; structuring writes canonical `wiki_entries`

### Mathesys outputs

- `artifacts` — `electronic_book`, `narration_audio`, `wiki_json`, `study_material` (table rows; files live under `sources`)
- `study_materials`, `study_material_components`, `study_material_component_versions` — Design tab drafts, their per-section components (with uploaded input files), and every generated component version
- `narration_segments` — per-paragraph rows keyed by model, voice, and source-text hash, pointing at chapter (or chapter-split) audio paths and validated word timings
- Storage bucket: `sources` — `{workspace_slug}/{source_slug}/` holds the
  original upload, downloadable outputs (`book.epub`, `narration.json`,
  `wiki.json`), Reader audio under
  `audio/{provider}/{model_id}/{voice_id}/`, and
  pipeline scratch under `work/`. Wiki note drafts: `{workspace_slug}/drafts/`.
  Study Material: `{workspace_slug}/study-material/{slug}/` (component inputs, generated
  images, `material.html`, `material.pdf`).
  Frozen unique slugs; API ids stay UUIDs.

### QnGen assessments

- `assessment_sets` — canonical linked assessment JSON
- `flashcards`, `quizzes`, `scenarios` — denormalized promoted items

### Assistant

- `discussion_threads`, `discussion_messages` — persisted Discussions conversations

### Seeded stages

Stage versions use **major.minor** format only (`1.0`, `2.0` — never `1.0.0`).

To repair a wiped or stale `stages` table on an existing project, re-run `supabase/setup/03-seed-stages.sql` (idempotent upsert). See `restore-stages.sql` for the short operator note.

| Module | Stage ID | Version |
|--------|----------|---------|
| intellex | `parse` | 1.0 |
| intellex | `normalize-document` | 1.0, **1.1** (pipeline) |
| intellex | `trim-document-boundaries` | 1.0 |
| intellex | `structure-document` | 1.0, 1.1, 1.2, **1.3** (pipeline) |
| intellex | `validate-structure` | 1.0 |
| intellex | `source-research` | 1.0, 2.0, **2.1** (pipeline) |
| intellex | `web-enrichment` | **1.0** (pipeline) |
| intellex | `transcribe-wiki-notes` | **1.0** (pipeline) |
| intellex | `structure-wiki-notes` | **1.0** (pipeline) |
| intellex | `prepare-document` | 1.0, 2.0 (deactivated) |
| intellex | `deconstruct-document` | 1.0, 2.0 (deactivated) |
| intellex | `extract-knowledge` | 1.0, 2.1 (deactivated — wiki is curated) |
| mathesys | `create-ebook` | 1.0 |
| mathesys | `export-wiki-json` | 1.0 |
| mathesys | `generate-narration` | 1.0 |
| mathesys | `generate-diagrams` | **1.0** (Study Material) |
| mathesys | `generate-images` | **1.0** (Study Material) |
| mathesys | `generate-text` | **1.0** (Study Material) |
| mathesys | `orchestrate-layout` | **1.0** (Study Material) |
| mathesys | `elevenreader-ebook` | 1.0, 2.0 (deactivated) |
| mathesys | `speechify-audio` | 1.0 (deactivated) |
| mathesys | `elevenlabs-audio` | 1.0 (deactivated) |
| qngen | `generate-flashcards` | 1.0, **2.1** |
| qngen | `generate-questions` | 1.0, **2.1** |
| qngen | `generate-scenarios` | 1.0, **2.1** |

The active ingest pipeline uses structuring stages + `source-research` 2.1 + `web-enrichment` 1.0. Older stage versions are kept for foreign-key compatibility with historical `stage_runs`.

**Note:** `source-research` 2.1 and `web-enrichment` 1.0 are required by the current API pipeline. They are seeded here for greenfield installs; existing projects may still need those two rows inserted manually (or via this seed file).

## Fresh vs existing

| Path | Use when |
|------|----------|
| `01`–`04` above | New project, greenfield install |
| `alter-*.sql` / `restore-stages.sql` | Existing project that needs a targeted patch |
