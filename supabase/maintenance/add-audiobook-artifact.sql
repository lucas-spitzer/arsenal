-- Allow a directly uploaded audiobook MP3 as a library artifact.
-- Fresh installs already include this check in supabase/setup/02-schema.sql.

alter table public.artifacts
  drop constraint artifacts_type_check;

alter table public.artifacts
  add constraint artifacts_type_check
  check (
    artifact_type in (
      'electronic_book',
      'narration_audio',
      'wiki_json',
      'study_material',
      'audiobook'
    )
  );
