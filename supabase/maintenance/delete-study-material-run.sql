-- Operator cleanup: remove one Study Material production run and the rows it owns.
--
-- production_runs children use ON DELETE SET NULL, so deleting the run row
-- alone leaves the study material, its components, versions, artifacts, and
-- stage_runs. Component versions also point at the component's
-- active_version_id, so the material cannot be dropped until that link is
-- cleared.
--
-- The study material currently attached to this run is deleted with it,
-- including uploaded component files and the sources-bucket folder
-- {workspace}/{study-material}/{slug}/. A material that has since been
-- pointed at a newer run is left in place; only this run's versions,
-- artifacts, and stage_runs are removed.
--
-- Supabase blocks DELETE on storage.objects from SQL. Leftover file keys are
-- listed in notices and in pg_temp.purge_storage_paths. Remove them from the
-- sources bucket in Dashboard → Storage, or via the Storage API.
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

  run_row public.production_runs%rowtype;
  material_ids uuid[] := '{}';
  version_ids uuid[] := '{}';
  artifact_ids uuid[] := '{}';
  storage_names text[] := '{}';
  study_stage_ids text[] := array[
    'generate-diagrams',
    'generate-images',
    'generate-text',
    'orchestrate-layout'
  ];
  material public.study_materials%rowtype;
  n integer;
  leftover text;
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

  select coalesce(array_agg(distinct id), '{}')
  into material_ids
  from (
    select sm.id
    from public.study_materials sm
    where sm.production_run_id = target_run_id
    union
    select sm.id
    from public.study_materials sm
    join public.artifacts a on a.id = sm.artifact_id
    where a.production_run_id = target_run_id
      and (sm.production_run_id is null or sm.production_run_id = target_run_id)
    union
    select sm.id
    from (
      select distinct sr.inputs->>'study_material_id' as material_id
      from public.stage_runs sr
      where sr.production_run_id = target_run_id
        and sr.inputs->>'study_material_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ) linked
    join public.study_materials sm on sm.id = linked.material_id::uuid
    where sm.production_run_id is null
       or sm.production_run_id = target_run_id
  ) owned;

  if not (
    'study_material' = any (run_row.target_artifacts)
    or material_ids <> '{}'::uuid[]
    or exists (
      select 1
      from public.stage_runs sr
      where sr.production_run_id = target_run_id
        and sr.stage_id = any (study_stage_ids)
    )
    or exists (
      select 1
      from public.artifacts a
      where a.production_run_id = target_run_id
        and a.artifact_type = 'study_material'
    )
  ) then
    raise exception
      'production_run % is not a study material run (targets=%). Use delete-production-run.sql.',
      target_run_id,
      run_row.target_artifacts;
  end if;

  raise notice 'production_run % workspace=% status=% label=% targets=%',
    run_row.id,
    run_row.workspace_id,
    run_row.status,
    run_row.label,
    run_row.target_artifacts;

  if run_row.status in ('queued', 'running') then
    raise notice 'run status is %; stop the worker job before deleting', run_row.status;
  end if;

  for material in
    select sm.*
    from public.study_materials sm
    where sm.id = any (material_ids)
    order by sm.created_at
  loop
    raise notice 'study_material % title=% status=% slug=%',
      material.id,
      material.title,
      material.status,
      material.slug;
  end loop;

  select coalesce(array_agg(distinct id), '{}')
  into version_ids
  from (
    select v.id
    from public.study_material_component_versions v
    where v.study_material_id = any (material_ids)
    union
    select v.id
    from public.study_material_component_versions v
    join public.stage_runs sr on sr.id = v.stage_run_id
    where sr.production_run_id = target_run_id
  ) owned_versions;

  select coalesce(array_agg(distinct id), '{}')
  into artifact_ids
  from (
    select a.id
    from public.artifacts a
    where a.production_run_id = target_run_id
       or a.origin->>'production_run_id' = target_run_id::text
       or (
         a.origin->>'study_material_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         and (a.origin->>'study_material_id')::uuid = any (material_ids)
       )
    union
    select sm.artifact_id
    from public.study_materials sm
    where sm.id = any (material_ids)
      and sm.artifact_id is not null
  ) owned_artifacts
  where not exists (
    select 1
    from public.study_materials other
    where other.artifact_id = owned_artifacts.id
      and other.id <> all (material_ids)
  );

  select coalesce(array_agg(distinct path), '{}')
  into storage_names
  from (
    select so.name as path
    from public.study_materials sm
    join public.workspaces w on w.id = sm.workspace_id
    join storage.objects so
      on so.bucket_id = 'sources'
     and so.name like (
       replace(replace(w.slug || '/study-material/' || sm.slug, '%', '\%'), '_', '\_')
       || '/%'
     ) escape '\'
    where sm.id = any (material_ids)
    union
    select sm.final_html_path
    from public.study_materials sm
    where sm.id = any (material_ids)
      and coalesce(sm.final_html_path, '') <> ''
    union
    select file->>'storage_path'
    from public.study_material_components c
    cross join lateral jsonb_array_elements(coalesce(c.files, '[]'::jsonb)) file
    where c.study_material_id = any (material_ids)
      and coalesce(file->>'storage_path', '') <> ''
    union
    select v.output_path
    from public.study_material_component_versions v
    where v.id = any (version_ids)
      and coalesce(v.output_path, '') <> ''
    union
    select a.storage_path
    from public.artifacts a
    where a.id = any (artifact_ids)
      and coalesce(a.storage_path, '') <> ''
      and a.storage_path <> 'pending'
  ) paths;

  select count(*) into n
  from public.study_material_components
  where study_material_id = any (material_ids);
  raise notice 'study_materials: %', coalesce(cardinality(material_ids), 0);
  raise notice 'study_material_components: %', n;
  raise notice 'study_material_component_versions: %', coalesce(cardinality(version_ids), 0);
  raise notice 'artifacts: %', coalesce(cardinality(artifact_ids), 0);

  select count(*) into n
  from public.stage_runs
  where production_run_id = target_run_id;
  raise notice 'stage_runs: %', n;
  raise notice 'storage objects to consider: %', coalesce(cardinality(storage_names), 0);

  if dry_run then
    raise exception
      'dry_run is true; production_run % was not deleted. Set dry_run false and run again.',
      target_run_id;
  end if;

  update public.study_material_components
  set active_version_id = null
  where active_version_id = any (version_ids)
     or study_material_id = any (material_ids);
  get diagnostics n = row_count;
  raise notice 'cleared active_version_id: %', n;

  delete from public.study_material_component_versions
  where id = any (version_ids);
  get diagnostics n = row_count;
  raise notice 'deleted study_material_component_versions: %', n;

  delete from public.study_material_components
  where study_material_id = any (material_ids);
  get diagnostics n = row_count;
  raise notice 'deleted study_material_components: %', n;

  update public.study_materials
  set artifact_id = null
  where id = any (material_ids)
     or artifact_id = any (artifact_ids);
  get diagnostics n = row_count;
  raise notice 'cleared study_materials.artifact_id: %', n;

  delete from public.artifacts
  where id = any (artifact_ids);
  get diagnostics n = row_count;
  raise notice 'deleted artifacts: %', n;

  delete from public.study_materials
  where id = any (material_ids);
  get diagnostics n = row_count;
  raise notice 'deleted study_materials: %', n;

  delete from public.stage_runs
  where production_run_id = target_run_id;
  get diagnostics n = row_count;
  raise notice 'deleted stage_runs: %', n;

  delete from public.production_runs
  where id = target_run_id;
  get diagnostics n = row_count;
  raise notice 'deleted production_runs: %', n;

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
        select 1 from public.study_materials sm where sm.final_html_path = so.name
      )
      and not exists (
        select 1
        from public.study_material_component_versions v
        where v.output_path = so.name
      )
      and not exists (
        select 1
        from public.study_material_components c
        cross join lateral jsonb_array_elements(coalesce(c.files, '[]'::jsonb)) file
        where file->>'storage_path' = so.name
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
