-- Design Image stage default: quality.
-- Safe to re-run. Fresh installs from 02-schema.sql already include image_quality.

alter table public.workspace_stage_settings
  add column if not exists image_quality text;

alter table public.workspace_stage_settings
  drop column if exists image_resolution;
