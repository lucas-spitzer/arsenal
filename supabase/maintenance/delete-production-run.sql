-- Operator cleanup: remove one production run and the rows it created.
--
-- Foreign keys on production_run_id are ON DELETE SET NULL, so deleting the
-- run row alone leaves assessments, artifacts, wiki batches, and stage_runs.
-- This script deletes those children. Tables that are in 02-schema.sql but
-- missing on a patched database (for example assessment_sets) are skipped.
--
-- Supabase blocks DELETE on storage.objects from SQL. Leftover file keys are
-- listed in notices and in pg_temp.purge_storage_paths. Remove them from the
-- sources bucket in Dashboard → Storage, or via the Storage API.
--
-- It does not delete source rows or original uploads. Intellex structure
-- (ndr_segments, document_chapters, work/) is source-level and reused by
-- later runs, so it stays unless purge_ingest is true.
--
-- Usage (SQL editor or `supabase db execute --file`):
--   1. Set target_run_id.
--   2. Leave dry_run true. The first run should error with a preview.
--   3. Set dry_run false and run again to delete rows.
--   4. If the run is still queued or running, stop the worker job first.

do $purge$
declare
  target_run_id uuid := '00000000-0000-0000-0000-000000000000';
  dry_run boolean := true;
  purge_ingest boolean := false;

  run_row public.production_runs%rowtype;
  wiki_ids uuid[] := '{}';
  narration_ids uuid[] := '{}';
  ingest_source_ids uuid[] := '{}';
  storage_names text[] := '{}';
  run_owned_tables text[] := array[
    'flashcards',
    'quizzes',
    'scenarios',
    'assessment_sets',
    'wiki_ingest_batches',
    'artifacts',
    'stage_runs'
  ];
  rel text;
  leftover text;
  n integer;
begin
  if target_run_id = '00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'Set target_run_id to the production_runs.id you want to remove.';
  end if;

  select * into run_row
  from public.production_runs
  where id = target_run_id;

  if not found then
    raise exception 'production_run % not found', target_run_id;
  end if;

  raise notice 'production_run % workspace=% status=% targets=% sources=%',
    run_row.id,
    run_row.workspace_id,
    run_row.status,
    run_row.target_artifacts,
    run_row.source_ids;

  select coalesce(array_agg(distinct entry_id), '{}')
  into wiki_ids
  from (
    select we.id as entry_id
    from public.wiki_entries we
    where we.origin->>'production_run_id' = target_run_id::text
      and we.created_at >= run_row.created_at
    union
    select inserted_id::uuid
    from public.stage_runs sr
    cross join lateral jsonb_array_elements_text(
      coalesce(sr.output->'inserted_ids', '[]'::jsonb)
    ) as inserted_id
    where sr.production_run_id = target_run_id
      and sr.stage_id = 'structure-wiki-notes'
      and inserted_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  ) created_wiki;

  select coalesce(array_agg(ns.id), '{}')
  into narration_ids
  from public.narration_segments ns
  join public.stage_runs sr
    on sr.production_run_id = target_run_id
   and sr.stage_id = 'generate-narration'
   and ns.source_id = nullif(sr.inputs->>'source_id', '')::uuid
   and ns.voice_id = sr.inputs->>'voice_id'
   and ns.model_id = sr.inputs->>'model_id'
  where not exists (
    select 1
    from public.artifacts a
    where a.production_run_id is distinct from target_run_id
      and a.source_id = ns.source_id
      and a.artifact_type = 'narration_audio'
      and a.manifest->>'voice_id' = ns.voice_id
      and a.manifest->>'model_id' = ns.model_id
  );

  if purge_ingest then
    select coalesce(array_agg(src_id), '{}')
    into ingest_source_ids
    from unnest(run_row.source_ids) as src_id
    where not exists (
      select 1
      from public.production_runs other
      where other.id <> target_run_id
        and src_id = any (other.source_ids)
    );
  end if;

  select coalesce(array_agg(distinct path), '{}')
  into storage_names
  from (
    select a.storage_path as path
    from public.artifacts a
    where a.production_run_id = target_run_id
      and coalesce(a.storage_path, '') <> ''
      and a.storage_path <> 'pending'
    union
    select ns.audio_path
    from public.narration_segments ns
    where ns.id = any (narration_ids)
      and coalesce(ns.audio_path, '') <> ''
    union
    select att->>'storage_path'
    from public.wiki_ingest_batches b
    cross join lateral jsonb_array_elements(coalesce(b.attachments, '[]'::jsonb)) att
    where b.production_run_id = target_run_id
      and coalesce(att->>'storage_path', '') <> ''
      and not exists (
        select 1
        from public.sources s
        where s.storage_path = att->>'storage_path'
      )
    union
    select so.name
    from public.sources s
    join public.workspaces w on w.id = s.workspace_id
    join storage.objects so
      on so.bucket_id = 'sources'
     and so.name like w.slug || '/' || s.slug || '/work/%'
    where s.id = any (ingest_source_ids)
  ) paths;

  foreach rel in array run_owned_tables loop
    if to_regclass('public.' || rel) is null then
      raise notice '%: skipped (table missing)', rel;
      continue;
    end if;
    execute format(
      'select count(*) from public.%I where production_run_id = $1',
      rel
    ) into n using target_run_id;
    raise notice '%: %', rel, n;
  end loop;
  raise notice 'wiki_entries created by this run: %', coalesce(cardinality(wiki_ids), 0);
  raise notice 'narration_segments owned by this run: %', coalesce(cardinality(narration_ids), 0);
  raise notice 'storage objects to consider: %', coalesce(cardinality(storage_names), 0);
  if purge_ingest then
    raise notice 'ingest sources eligible to wipe: %', ingest_source_ids;
  end if;

  if dry_run then
    raise exception
      'dry_run is true; production_run % was not deleted. Set dry_run false and run again.',
      target_run_id;
  end if;

  foreach rel in array array[
    'flashcards',
    'quizzes',
    'scenarios',
    'assessment_sets'
  ] loop
    if to_regclass('public.' || rel) is null then
      raise notice 'deleted %: skipped (table missing)', rel;
      continue;
    end if;
    execute format(
      'delete from public.%I where production_run_id = $1',
      rel
    ) using target_run_id;
    get diagnostics n = row_count;
    raise notice 'deleted %: %', rel, n;
  end loop;

  delete from public.wiki_disputes
  where stage_run_id in (
    select id from public.stage_runs where production_run_id = target_run_id
  );
  get diagnostics n = row_count;
  raise notice 'deleted wiki_disputes: %', n;

  if wiki_ids <> '{}'::uuid[] then
    update public.wiki_entries we
    set prerequisites = coalesce((
      select array_agg(prereq_id)
      from unnest(we.prerequisites) as prereq_id
      where prereq_id <> all (wiki_ids)
    ), '{}')
    where we.prerequisites && wiki_ids;
    get diagnostics n = row_count;
    raise notice 'cleared wiki prerequisites on other entries: %', n;

    delete from public.wiki_entries where id = any (wiki_ids);
    get diagnostics n = row_count;
    raise notice 'deleted wiki_entries: %', n;
  end if;

  delete from public.wiki_ingest_batches where production_run_id = target_run_id;
  get diagnostics n = row_count;
  raise notice 'deleted wiki_ingest_batches: %', n;

  delete from public.artifacts where production_run_id = target_run_id;
  get diagnostics n = row_count;
  raise notice 'deleted artifacts: %', n;

  if narration_ids <> '{}'::uuid[] then
    delete from public.narration_segments where id = any (narration_ids);
    get diagnostics n = row_count;
    raise notice 'deleted narration_segments: %', n;
  end if;

  if ingest_source_ids <> '{}'::uuid[] then
    delete from public.narration_segments where source_id = any (ingest_source_ids);
    delete from public.document_chapters where source_id = any (ingest_source_ids);
    get diagnostics n = row_count;
    raise notice 'deleted document_chapters: %', n;
    delete from public.ndr_segments where source_id = any (ingest_source_ids);
    get diagnostics n = row_count;
    raise notice 'deleted ndr_segments: %', n;
    update public.sources
    set status = 'stored'
    where id = any (ingest_source_ids)
      and status <> 'stored';
  end if;

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
      and not exists (
        select 1 from public.artifacts a where a.storage_path = so.name
      )
      and not exists (
        select 1 from public.narration_segments ns where ns.audio_path = so.name
      )
      and not exists (
        select 1 from public.sources s where s.storage_path = so.name
      )
      and not exists (
        select 1
        from public.wiki_ingest_batches b
        cross join lateral jsonb_array_elements(coalesce(b.attachments, '[]'::jsonb)) att
        where att->>'storage_path' = so.name
      );
    get diagnostics n = row_count;
    raise notice 'storage objects left for Storage API delete: %', n;
    for leftover in
      select p.name from pg_temp.purge_storage_paths p order by p.name
    loop
      raise notice 'leftover storage object: sources/%', leftover;
    end loop;
  end if;

  delete from public.stage_runs where production_run_id = target_run_id;
  get diagnostics n = row_count;
  raise notice 'deleted stage_runs: %', n;

  delete from public.production_runs where id = target_run_id;
  get diagnostics n = row_count;
  raise notice 'deleted production_runs: %', n;
end
$purge$;

select bucket, name
from pg_temp.purge_storage_paths
order by name;
