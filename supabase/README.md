# Foundry Supabase

Database bootstrap for Foundry.

| Path | Use when |
|------|----------|
| [`setup/`](setup/README.md) `01`–`04` | New Supabase project — greenfield install |
| [`setup/`](setup/README.md) `alter-*.sql` | Existing database — targeted additive patches |

## Prerequisites

- **Google OAuth** configured in Supabase Auth (required for sign-in).
- The FastAPI backend uses the **service role** key for data access in V1. Client roles are revoked from application tables.

After setup, replace the placeholder owner email in `approved_users` with your own Google account address.

---

## New project setup

For a fresh Supabase project, run the consolidated scripts in [`setup/`](setup/README.md). They create the full current schema and stage seeds.

```text
supabase/setup/01-auth-and-extensions.sql
supabase/setup/02-schema.sql
supabase/setup/03-seed-stages.sql
supabase/setup/04-storage-and-rls.sql
```

Run them in order in the Supabase SQL editor, or with the CLI linked to your project:

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

Do **not** glob `supabase/setup/*.sql` — operator patches (`alter-*.sql`, `restore-stages.sql`) must not run as part of a fresh install.

See [`setup/README.md`](setup/README.md) for the full inventory of tables, buckets, seeded stages, and existing-database patches.

---

## Existing databases

Do **not** re-run `01`–`04` on a database that already has Foundry tables. Apply the relevant operator patch from `setup/` instead:

| File | Purpose |
|------|---------|
| `alter-wiki-ingest-file-ingest.sql` | Wiki file-ingest columns + transcription statuses on `wiki_ingest_batches` |
| `../maintenance/alter-study-material.sql` | Study Material tables, stages, bucket MIME types, and the `study_sheet` → `study_material` artifact type swap |
| `alter-drop-artifacts-bucket.sql` | Docs only — purge legacy `artifacts` storage bucket via Storage API / Dashboard after migrating into `sources` |
| `restore-stages.sql` | Re-run `03-seed-stages.sql` to repair `stages` |

Details and commands: [`setup/README.md`](setup/README.md#existing-database-patches).
