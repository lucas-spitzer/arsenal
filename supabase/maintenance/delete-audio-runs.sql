-- Operator cleanup: remove audio runs and audio files in The Basic School.
--
-- Other workspaces are left alone. Tables, stages, TTS settings, sources,
-- and non-audio runs stay. This deletes the rows the Library and Foundry
-- use to show audio in that workspace:
--
--   * production runs whose only target is narration_audio, and every
--     stage_run on those runs
--   * generate-narration stage_runs on mixed runs, with narration_audio
--     removed from those runs' targets and pipeline
--   * narration_audio and audiobook artifact rows
--   * narration_segments
--
-- Sources, ndr_segments, document_chapters, books, wiki, assessments, and
-- study material stay. So does work/ under each source.
--
-- Supabase blocks DELETE on storage.objects from SQL. Leftover file keys
-- are listed in notices and in pg_temp.purge_storage_paths. Remove them
-- from the sources bucket in Dashboard → Storage, or via the Storage API.
-- That includes narration.json, clip wavs, combined book.mp3 files, and
-- uploaded audiobook mp3s under this workspace's slug.
--
-- Usage (SQL editor or `supabase db execute --file`):
--   1. Stop the worker if any narration run in this workspace is queued
--      or running.
--   2. Leave dry_run true. The first run should error with a preview.
--   3. Set dry_run false and run again to delete rows.
--   4. Delete the listed storage keys.

do $purge$
declare
  dry_run boolean := true;
  target_workspace_name text := 'The Basic School';

  target_workspace_id uuid;
  workspace_slug text;
  storage_prefix text;
  audio_run_ids uuid[] := '{}';
  mixed_run_ids uuid[] := '{}';
  storage_names text[] := '{}';
  busy boolean := false;
  run_row public.production_runs%rowtype;
  n integer;
  leftover text;
begin
  select id, slug
  into target_workspace_id, workspace_slug
  from public.workspaces
  where name = target_workspace_name;

  if not found then
    raise exception 'Workspace % not found.', target_workspace_name;
  end if;

  storage_prefix := replace(replace(workspace_slug, '%', '\%'), '_', '\_') || '/';

  raise notice 'workspace % (%) slug=%',
    target_workspace_name,
    target_workspace_id,
    workspace_slug;

  select coalesce(array_agg(id), '{}')
  into audio_run_ids
  from public.production_runs
  where workspace_id = target_workspace_id
    and 'narration_audio' = any (target_artifacts)
    and target_artifacts <@ array['narration_audio']::text[];

  select coalesce(array_agg(id), '{}')
  into mixed_run_ids
  from public.production_runs
  where workspace_id = target_workspace_id
    and 'narration_audio' = any (target_artifacts)
    and not (target_artifacts <@ array['narration_audio']::text[]);

  select exists (
    select 1
    from public.production_runs
    where workspace_id = target_workspace_id
      and id = any (audio_run_ids || mixed_run_ids)
      and status in ('queued', 'running')
    union all
    select 1
    from public.stage_runs
    where workspace_id = target_workspace_id
      and stage_id = 'generate-narration'
      and status in ('queued', 'running')
  )
  into busy;

  if busy then
    raise notice
      'A narration run in % is still queued or running. Stop the worker before deleting.',
      target_workspace_name;
  end if;

  for run_row in
    select *
    from public.production_runs
    where id = any (audio_run_ids)
    order by created_at
  loop
    raise notice 'audio-only run % status=% targets=% sources=%',
      run_row.id,
      run_row.status,
      run_row.target_artifacts,
      run_row.source_ids;
  end loop;

  for run_row in
    select *
    from public.production_runs
    where id = any (mixed_run_ids)
    order by created_at
  loop
    raise notice 'mixed run % keeps non-audio output; narration stripped. status=% targets=%',
      run_row.id,
      run_row.status,
      run_row.target_artifacts;
  end loop;

  select count(*) into n
  from public.narration_segments
  where workspace_id = target_workspace_id;
  raise notice 'narration_segments: %', n;

  select count(*) into n
  from public.artifacts
  where workspace_id = target_workspace_id
    and artifact_type in ('narration_audio', 'audiobook');
  raise notice 'audio artifacts: %', n;

  select count(*) into n
  from public.stage_runs
  where workspace_id = target_workspace_id
    and (
      stage_id = 'generate-narration'
      or production_run_id = any (audio_run_ids)
    );
  raise notice 'stage_runs to delete: %', n;

  raise notice 'audio-only production_runs: %', coalesce(cardinality(audio_run_ids), 0);
  raise notice 'mixed production_runs to strip: %', coalesce(cardinality(mixed_run_ids), 0);

  select coalesce(array_agg(distinct path), '{}')
  into storage_names
  from (
    select a.storage_path as path
    from public.artifacts a
    where a.workspace_id = target_workspace_id
      and a.artifact_type in ('narration_audio', 'audiobook')
      and coalesce(a.storage_path, '') <> ''
      and a.storage_path <> 'pending'
    union
    select a.manifest->>'combined_audio_path'
    from public.artifacts a
    where a.workspace_id = target_workspace_id
      and a.artifact_type = 'narration_audio'
      and coalesce(a.manifest->>'combined_audio_path', '') <> ''
    union
    select ns.audio_path
    from public.narration_segments ns
    where ns.workspace_id = target_workspace_id
      and coalesce(ns.audio_path, '') <> ''
    union
    select so.name
    from storage.objects so
    where so.bucket_id = 'sources'
      and so.name like storage_prefix || '%' escape '\'
      and (
        so.name like storage_prefix || '%/audio/%' escape '\'
        or so.name like storage_prefix || '%/audiobooks/%' escape '\'
        or so.name like storage_prefix || '%/narration.json' escape '\'
      )
  ) paths
  where not exists (
    select 1 from public.sources s where s.storage_path = paths.path
  );

  raise notice 'storage objects to consider: %', coalesce(cardinality(storage_names), 0);

  if dry_run then
    raise exception
      'dry_run is true; audio runs and files in % were not deleted. Set dry_run false and run again.',
      target_workspace_name;
  end if;

  if busy then
    raise exception
      'A narration run in % is still queued or running. Stop the worker, then run this again.',
      target_workspace_name;
  end if;

  delete from public.narration_segments
  where workspace_id = target_workspace_id;
  get diagnostics n = row_count;
  raise notice 'deleted narration_segments: %', n;

  delete from public.artifacts
  where workspace_id = target_workspace_id
    and artifact_type in ('narration_audio', 'audiobook');
  get diagnostics n = row_count;
  raise notice 'deleted artifacts: %', n;

  delete from public.stage_runs
  where workspace_id = target_workspace_id
    and (
      stage_id = 'generate-narration'
      or production_run_id = any (audio_run_ids)
    );
  get diagnostics n = row_count;
  raise notice 'deleted stage_runs: %', n;

  delete from public.production_runs
  where workspace_id = target_workspace_id
    and id = any (audio_run_ids);
  get diagnostics n = row_count;
  raise notice 'deleted production_runs: %', n;

  update public.production_runs pr
  set
    target_artifacts = array_remove(pr.target_artifacts, 'narration_audio'),
    pipeline = coalesce((
      select jsonb_agg(t.step order by t.ord)
      from jsonb_array_elements(pr.pipeline) with ordinality as t(step, ord)
      where coalesce(t.step->>'stage_id', '') <> 'generate-narration'
        and coalesce(t.step->>'step', '') <> 'generate-narration'
    ), '[]'::jsonb),
    updated_at = now()
  where pr.workspace_id = target_workspace_id
    and pr.id = any (mixed_run_ids);
  get diagnostics n = row_count;
  raise notice 'stripped narration from mixed production_runs: %', n;

  drop table if exists pg_temp.purge_storage_paths;
  create temp table pg_temp.purge_storage_paths (
    bucket text not null,
    name text not null
  );

  if storage_names <> '{}'::text[] then
    insert into pg_temp.purge_storage_paths (bucket, name)
    select 'sources', so.name
    from storage.objects so
    where so.bucket_id = 'sources'
      and so.name = any (storage_names)
      and so.name like storage_prefix || '%' escape '\'
      and not exists (
        select 1 from public.artifacts a where a.storage_path = so.name
      )
      and not exists (
        select 1
        from public.artifacts a
        where a.manifest->>'combined_audio_path' = so.name
      )
      and not exists (
        select 1 from public.narration_segments ns where ns.audio_path = so.name
      )
      and not exists (
        select 1 from public.sources s where s.storage_path = so.name
      );
    get diagnostics n = row_count;
    raise notice 'storage objects left for Storage API delete: %', n;
    for leftover in
      select p.name from pg_temp.purge_storage_paths p order by p.name
    loop
      raise notice 'leftover storage object: sources/%', leftover;
    end loop;
  end if;
end
$purge$;

select bucket, name
from pg_temp.purge_storage_paths
order by name;
