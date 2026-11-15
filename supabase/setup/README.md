# Foundry Supabase Setup

Use the numbered scripts (`01`–`04`) to bootstrap a **fresh** Supabase project. They contain the full current schema and stage seeds.

Operator patches (`alter-*.sql`, `restore-stages.sql`) are for **existing** databases only — do not include them in the greenfield loop.

## Prerequisites

- A Supabase project with **Google OAuth** configured in Auth.
- Custom SMTP and the Magic Link template in [Email sign-in codes](#email-sign-in-codes), so an approved address that is not a Google account can receive a code.
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

After running setup, insert your own Google account address into `approved_users` as `admin`. The setup script does not insert one. If an earlier run left a placeholder address in that table, deactivate that row in the Supabase dashboard.

## Email sign-in codes

Google stays available. `POST /auth/email-code` returns 204 for any well-formed address. It sends an 8-digit code only when the address is an active `approved_users` row. The sign-in page then calls `verifyOtp`.

Configure custom SMTP in the Supabase dashboard. Do not commit the SMTP password or API key.

Then:

1. Authentication → Sign In / Providers → Email: leave **Email OTP length** at `8`. That control is on the Email provider page, not on Emails. The sign-in form accepts 8 digits.
2. Authentication → Emails → Templates → open **Magic link or OTP**. The subject field is on that page. Set it to `Your Arsenal sign-in code`.
3. Replace the template body with the full file [`sign-in-code-email.html`](sign-in-code-email.html). Copy the file as-is, including `{{ .Token }}`. The code is text in the message. Do not put it in a link, do not add letter-spacing around the code, and do not add `{{ .ConfirmationURL }}`. Outlook and Defender prefetch links and consume a sign-in link.
4. Leave Email OTP expiration at the dashboard default. Do not set it above one day.

The message follows the style guide: a navy band, a scarlet rule, a scarlet Arial heading, the code in one monospace run with no letter-spacing, a gold divider, and a gray line that says Arsenal is an unofficial study tool and not a United States Marine Corps website. No Marine Corps mark.

## Existing database patches

Run these only on databases that already have a Foundry schema and need a targeted upgrade. Fresh installs from `01`–`04` already include the current shape.

| File | When to run |
|------|-------------|
| `../maintenance/alter-study-material.sql` | DB was created before Study Material. Adds `production_runs.label`, the `study_materials` / `study_material_components` / `study_material_component_versions` tables with RLS + revokes, swaps `study_sheet` for `study_material` in `artifacts_type_check`, widens the `sources` bucket MIME list (text, CSV, HTML, PNG, JPEG, WebP), and seeds the four Study Material stages. Idempotent. |
| `alter-library-slugs.sql` | DB was created before frozen workspace/source slugs. Adds `workspaces.slug`, unique workspace names, and `sources.slug`. |
| `../maintenance/alter-knowledge-plan-layout.sql` | DB was created before flashcard layouts. Adds `knowledge_item_plans.layout`. Idempotent. |
| `../maintenance/alter-answer-pool.sql` | DB was created before the knowledge composer. Adds `quizzes.answer_pool`, `quizzes.bloom_level`, `scenarios.bloom_level`, `knowledge_projects.batch_instructions`, `knowledge_item_plans.instructions` and `.draft`. Idempotent. |
| `../maintenance/alter-sources-kind.sql` | DB was created before structured data sources. Adds `sources.source_kind` (`document` or `structured_data`). Idempotent. |
| `alter-wiki-knowledge-pipeline.sql` | DB was created before wiki ingest as a production-run target. Adds `wiki_ingest_batches.production_run_id`. Re-run `03-seed-stages.sql` for the new wiki stages. |
| `alter-stage-settings-tts.sql` | DB was created before Speechify narration settings. Widens `workspace_stage_settings.provider` to include `speechify` / `elevenlabs` and adds nullable `voice_id`. |
| `alter-stage-settings-providers.sql` | DB was created before Google and Cartesia stage settings. Widens `workspace_stage_settings.provider` to include `google` / `cartesia`. |
| `../maintenance/alter-stage-settings-image-quality.sql` | DB was created before Design Image quality defaults. Adds nullable `workspace_stage_settings.image_quality` and drops `image_resolution` if it was added. |
| `../maintenance/alter-stage-settings-xai.sql` | DB was created before Grok Imagine stage settings. Widens `workspace_stage_settings.provider` to include `xai`. |
| `alter-sources-bucket-wav.sql` | DB was created before Cartesia/Gemini WAV clips. Adds `audio/wav` to the `sources` bucket allowlist. |
| `alter-drop-artifacts-bucket.sql` | Operator note only (SQL no-op). Supabase blocks dropping `storage.buckets` / `storage.objects` from SQL. After migrating objects into the `sources` bucket, purge the legacy `artifacts` bucket via the Storage API or Dashboard. |
| `alter-discussion-threads.sql` | DB was created before persisted discussion threads. Adds `discussion_threads` and `discussion_messages` with RLS + role revokes. Idempotent. |
| `alter-platoon-access.sql` | DB was created before admin and student access. Constrains `approved_users.role` to `admin` or `student` (existing `owner` rows become `admin`) and adds `discussion_threads.user_id`. |
| `alter-discussion-tbs.sql` | DB was created before the TBS discussion instruction. Allows `discussion_threads.submode` of `tbs` and defaults new threads to it. |
| `alter-wiki-entry-kind-elo.sql` | DB was created before Enabling Learning Objectives. Allows `wiki_entries.entry_kind` of `elo`. |
| `alter-calendar-events.sql` | DB was created before the Academics calendar. Adds `calendar_events` with RLS + role revokes. Idempotent. |
| `alter-calendar-schedule.sql` | DB was created before the Schedule tab and per-student task checks. Allows `calendar_events.kind` of `schedule` and adds `calendar_task_completions` with RLS + role revokes. Idempotent. |
| `alter-lessons.sql` | DB was created before the Academy ELO tab. Adds `lessons`, `lesson_objectives`, `lesson_resources`, `lesson_chunks`, `match_lesson_chunks`, `discussion_threads.lesson_id`, and the private `lesson-files` bucket, with RLS + role revokes. Idempotent. |
| `restore-stages.sql` | Short pointer: re-run `03-seed-stages.sql` to repair a wiped or stale `stages` table. The file stays on the machine that has it. |
| `../maintenance/add-audiobook-artifact.sql` | DB was created before direct audiobook uploads. Adds `audiobook` to `artifacts_type_check`. Idempotent aside from the constraint swap. |
| `../maintenance/add-quiz-results.sql` | DB was created before personal quiz results. Adds `quiz_results` with RLS and role revokes. Idempotent. |

Delete scripts and seed SQL stay on the machine that has them so they do not leak confidential information about the platform and its plans. See [`supabase/maintenance/README.md`](../maintenance/README.md).

### Academics calendar

```bash
supabase db execute --file supabase/setup/alter-calendar-events.sql
supabase db execute --file supabase/setup/alter-calendar-schedule.sql
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

### Design Image quality

```bash
supabase db execute --file supabase/maintenance/alter-stage-settings-image-quality.sql
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
- `wiki_entries` — canonical terms and lists (`entry_kind`; optional `significance`, `category`, and `items`)
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
- `quiz_results` — one finished quiz batch per row, visible only to the student who took it

### Academics calendar

- `calendar_events` — per-workspace deadlines, classes, prac apps, and evaluations (`event_date`, optional `start_time` / `end_time`, `location`, `notes`). Admins edit them in Foundry CAL; everyone reads them in Academy CAL.

### Academy ELO tab

- `lessons` — one row per TBS class (`title`, `sort_order`, `notes`).
- `lesson_objectives` — the class's ordered ELOs (`text`, `code` such as `MCS-MED-1001a`, `is_async`).
- `lesson_resources` — downloadable files in the `lesson-files` bucket or https links (MCeLE). Files carry `index_status` / `index_error` for Discussions search.
- `lesson_chunks` — extracted, embedded text from ELOs and lesson files. Searched by `match_lesson_chunks` alongside `ndr_segments` and `wiki_entries`. Not related to `wiki_entries` rows with `entry_kind = 'elo'`.

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

The active ingest pipeline uses structuring stages + `source-research` 2.1. `web-enrichment` 1.0 runs only on electronic-book production runs, immediately before `create-ebook`. Older stage versions are kept for foreign-key compatibility with historical `stage_runs`.

**Note:** `source-research` 2.1 and `web-enrichment` 1.0 are required by the current API pipeline. They are seeded here for greenfield installs; existing projects may still need those two rows inserted manually (or via this seed file).

## Fresh vs existing

| Path | Use when |
|------|----------|
| `01`–`04` above | New project, greenfield install |
| `alter-*.sql` / `restore-stages.sql` | Existing project that needs a targeted patch |
