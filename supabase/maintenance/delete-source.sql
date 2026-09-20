-- Operator cleanup: remove one source and the rows it created.
--
-- Most child FKs are ON DELETE SET NULL, so deleting the source row alone
-- leaves assessments, artifacts, wiki batches, disputes, and discussion
-- threads. This script deletes those children, then the source. Cascade
-- FKs (ndr_segments, document_chapters, narration_segments) go with the
-- source. Tables that are in 02-schema.sql but missing on a patched
-- database (for example assessment_sets) are skipped.
--
-- Wiki entries have no source_id column. Rows whose origin or remaining
-- evidence points only at this source are deleted. Shared wiki entries
-- drop this source from evidence and stay.
--
-- production_runs.source_ids is an array, not a FK. This script removes
-- the source id from those arrays. Empty or leftover runs are not deleted;
-- use delete-production-run.sql for that.
--
-- Supabase blocks DELETE on storage.objects from SQL. Leftover file keys
-- are listed in notices and in pg_temp.purge_storage_paths. Remove them
-- from the sources bucket in Dashboard → Storage, or via the Storage API.
--
-- Usage (SQL editor or `supabase db execute --file`):
--   1. Set target_source_id.
--   2. Leave dry_run true. The first run should error with a preview.
--   3. Set dry_run false and run again to delete rows.

do $purge$
declare
  target_source_id uuid := '00000000-0000-0000-0000-000000000000';
  dry_run boolean := true;

  source_row public.sources%rowtype;
  workspace_slug text;
  wiki_ids uuid[] := '{}';
  storage_names text[] := '{}';
  source_owned_tables text[] := array[
    'flashcards',
    'quizzes',
    'scenarios',
    'assessment_sets',
    'wiki_ingest_batches',
    'wiki_disputes',
    'artifacts',
    'discussion_threads'
  ];
  rel text;
  leftover text;
  n integer;
begin
  if target_source_id = '00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'Set target_source_id to the sources.id you want to remove.';
  end if;

  select * into source_row
  from public.sources
  where id = target_source_id;

  if not found then
    raise exception 'source % not found', target_source_id;
  end if;

  select w.slug into workspace_slug
  from public.workspaces w
  where w.id = source_row.workspace_id;

  raise notice 'source % workspace=% slug=% filename=% status=%',
    source_row.id,
    source_row.workspace_id,
    source_row.slug,
    source_row.filename,
    source_row.status;

  select coalesce(array_agg(we.id), '{}')
  into wiki_ids
  from public.wiki_entries we
  where we.origin->>'source_id' = target_source_id::text
     or (
       jsonb_typeof(we.evidence) = 'array'
       and exists (
         select 1
         from jsonb_array_elements(we.evidence) ev
         where ev->>'source_id' = target_source_id::text
       )
       and not exists (
         select 1
         from jsonb_array_elements(we.evidence) ev
         where coalesce(ev->>'source_id', '') <> ''
           and ev->>'source_id' <> target_source_id::text
       )
     );

  select coalesce(array_agg(distinct path), '{}')
  into storage_names
  from (
    select source_row.storage_path as path
    where coalesce(source_row.storage_path, '') <> ''
    union
    select a.storage_path
    from public.artifacts a
    where a.source_id = target_source_id
      and coalesce(a.storage_path, '') <> ''
      and a.storage_path <> 'pending'
    union
    select ns.audio_path
    from public.narration_segments ns
    where ns.source_id = target_source_id
      and coalesce(ns.audio_path, '') <> ''
    union
    select att->>'storage_path'
    from public.wiki_ingest_batches b
    cross join lateral jsonb_array_elements(coalesce(b.attachments, '[]'::jsonb)) att
    where b.source_id = target_source_id
      and coalesce(att->>'storage_path', '') <> ''
    union
    select so.name
    from storage.objects so
    where so.bucket_id = 'sources'
      and workspace_slug is not null
      and so.name like workspace_slug || '/' || source_row.slug || '/%'
  ) paths;

  foreach rel in array source_owned_tables loop
    if to_regclass('public.' || rel) is null then
      raise notice '%: skipped (table missing)', rel;
      continue;
    end if;
    execute format(
      'select count(*) from public.%I where source_id = $1',
      rel
    ) into n using target_source_id;
    raise notice '%: %', rel, n;
  end loop;
  raise notice 'ndr_segments: %',
    (select count(*) from public.ndr_segments where source_id = target_source_id);
  raise notice 'document_chapters: %',
    (select count(*) from public.document_chapters where source_id = target_source_id);
  raise notice 'narration_segments: %',
    (select count(*) from public.narration_segments where source_id = target_source_id);
  raise notice 'production_runs listing this source: %',
    (select count(*) from public.production_runs where target_source_id = any (source_ids));
  raise notice 'wiki_entries owned by this source: %', coalesce(cardinality(wiki_ids), 0);
  raise notice 'storage objects to consider: %', coalesce(cardinality(storage_names), 0);

  if dry_run then
    raise exception
      'dry_run is true; source % was not deleted. Set dry_run false and run again.',
      target_source_id;
  end if;

  foreach rel in array source_owned_tables loop
    if to_regclass('public.' || rel) is null then
      raise notice 'deleted %: skipped (table missing)', rel;
      continue;
    end if;
    execute format(
      'delete from public.%I where source_id = $1',
      rel
    ) using target_source_id;
    get diagnostics n = row_count;
    raise notice 'deleted %: %', rel, n;
  end loop;

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

  update public.wiki_entries we
  set evidence = coalesce((
    select jsonb_agg(ev)
    from jsonb_array_elements(we.evidence) ev
    where ev->>'source_id' is distinct from target_source_id::text
  ), '[]'::jsonb)
  where jsonb_typeof(we.evidence) = 'array'
    and exists (
      select 1
      from jsonb_array_elements(we.evidence) ev
      where ev->>'source_id' = target_source_id::text
    );
  get diagnostics n = row_count;
  raise notice 'scrubbed wiki evidence on remaining entries: %', n;

  update public.production_runs
  set source_ids = array_remove(source_ids, target_source_id)
  where target_source_id = any (source_ids);
  get diagnostics n = row_count;
  raise notice 'scrubbed production_runs.source_ids: %', n;

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
        select 1 from public.sources s
        where s.id <> target_source_id
          and s.storage_path = so.name
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

  delete from public.sources where id = target_source_id;
  get diagnostics n = row_count;
  raise notice 'deleted sources: %', n;
end
$purge$;

select bucket, name
from pg_temp.purge_storage_paths
order by name;
