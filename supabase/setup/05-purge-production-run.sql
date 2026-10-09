-- App delete for one production run and the rows it created.
--
-- Ports supabase/maintenance/delete-production-run.sql and
-- delete-study-material-run.sql. Study material runs take the study cascade.
-- A knowledge structure run that no later draft or visual run still uses takes
-- the project, its plans, notes, and images with it. A draft run removes the
-- questions and scenarios it created. Every other run takes the pipeline
-- cascade. Source rows, original uploads, and Intellex structure stay
-- (purge_ingest is off).
--
-- Foreign keys on production_run_id are ON DELETE SET NULL, so the run row
-- is deleted only after its children. Supabase blocks DELETE on
-- storage.objects from SQL. This function returns leftover keys in the
-- sources bucket; the API removes them with the Storage API.
--
-- Service role only. FastAPI checks ownership, then calls
-- rpc/purge_production_run.

create or replace function public.purge_production_run(p_run_id uuid)
returns table (bucket text, name text)
language plpgsql
security invoker
set search_path = public, storage
as $purge$
declare
  run_row public.production_runs%rowtype;
  is_study boolean := false;
  study_stage_ids text[] := array[
    'generate-diagrams',
    'generate-images',
    'generate-text',
    'orchestrate-layout'
  ];
  material_ids uuid[] := '{}';
  version_ids uuid[] := '{}';
  artifact_ids uuid[] := '{}';
  wiki_ids uuid[] := '{}';
  narration_ids uuid[] := '{}';
  storage_names text[] := '{}';
  drop_project_ids uuid[] := '{}';
  knowledge_paths text[] := '{}';
  run_owned_tables text[] := array[
    'flashcards',
    'quizzes',
    'scenarios',
    'assessment_sets'
  ];
  rel text;
begin
  select * into run_row
  from public.production_runs
  where id = p_run_id;

  if not found then
    raise exception 'production_run % not found', p_run_id;
  end if;

  select coalesce(array_agg(distinct id), '{}')
  into material_ids
  from (
    select sm.id
    from public.study_materials sm
    where sm.production_run_id = p_run_id
    union
    select sm.id
    from public.study_materials sm
    join public.artifacts a on a.id = sm.artifact_id
    where a.production_run_id = p_run_id
      and (sm.production_run_id is null or sm.production_run_id = p_run_id)
    union
    select sm.id
    from (
      select distinct sr.inputs->>'study_material_id' as material_id
      from public.stage_runs sr
      where sr.production_run_id = p_run_id
        and sr.inputs->>'study_material_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ) linked
    join public.study_materials sm on sm.id = linked.material_id::uuid
    where sm.production_run_id is null
       or sm.production_run_id = p_run_id
  ) owned;

  is_study :=
    'study_material' = any (run_row.target_artifacts)
    or material_ids <> '{}'::uuid[]
    or exists (
      select 1
      from public.stage_runs sr
      where sr.production_run_id = p_run_id
        and sr.stage_id = any (study_stage_ids)
    )
    or exists (
      select 1
      from public.artifacts a
      where a.production_run_id = p_run_id
        and a.artifact_type = 'study_material'
    );

  -- A structure run owns the project until a later draft or visual run exists.
  -- Dropping it removes the notes, plans, images, and drafted items. A draft
  -- run only removes the questions and scenarios that run added.
  if to_regclass('public.knowledge_projects') is not null then
    select coalesce(array_agg(kp.id), '{}')
    into drop_project_ids
    from public.knowledge_projects kp
    where kp.structure_run_id = p_run_id
      and (kp.draft_run_id is null or kp.draft_run_id = p_run_id)
      and (kp.visual_run_id is null or kp.visual_run_id = p_run_id);

    select coalesce(array_agg(distinct path), '{}')
    into knowledge_paths
    from (
      select kp.notes_storage_path as path
      from public.knowledge_projects kp
      where kp.id = any (drop_project_ids)
        and coalesce(kp.notes_storage_path, '') <> ''
      union
      select plan.visual->>'storage_path'
      from public.knowledge_item_plans plan
      where plan.knowledge_project_id = any (drop_project_ids)
        and coalesce(plan.visual->>'storage_path', '') <> ''
      union
      select item.visual->>'storage_path'
      from (
        select visual from public.flashcards
        where knowledge_project_id = any (drop_project_ids)
        union all
        select visual from public.quizzes
        where knowledge_project_id = any (drop_project_ids)
        union all
        select visual from public.scenarios
        where knowledge_project_id = any (drop_project_ids)
      ) item
      where coalesce(item.visual->>'storage_path', '') <> ''
      union
      select so.name
      from public.knowledge_projects kp
      join public.workspaces w on w.id = kp.workspace_id
      join public.sources s on s.id = kp.source_id
      join storage.objects so
        on so.bucket_id = 'sources'
       and (
         so.name like (
           replace(replace(w.slug || '/knowledge/' || kp.id::text, '%', '\%'), '_', '\_')
           || '/%'
         ) escape '\'
         or so.name like (
           replace(
             replace(w.slug || '/' || s.slug || '/knowledge/' || kp.id::text, '%', '\%'),
             '_',
             '\_'
           )
           || '/%'
         ) escape '\'
       )
      where kp.id = any (drop_project_ids)
    ) paths;

    delete from public.flashcards
    where knowledge_project_id = any (drop_project_ids);
    delete from public.quizzes
    where knowledge_project_id = any (drop_project_ids);
    delete from public.scenarios
    where knowledge_project_id = any (drop_project_ids);

    delete from public.knowledge_item_plans plan
    where plan.item_type in ('question', 'scenario')
      and plan.knowledge_project_id in (
        select kp.id
        from public.knowledge_projects kp
        where kp.draft_run_id = p_run_id
          and not (kp.id = any (drop_project_ids))
      );

    delete from public.knowledge_projects
    where id = any (drop_project_ids);
  end if;

  if is_study then
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
      where sr.production_run_id = p_run_id
    ) owned_versions;

    select coalesce(array_agg(distinct id), '{}')
    into artifact_ids
    from (
      select a.id
      from public.artifacts a
      where a.production_run_id = p_run_id
         or a.origin->>'production_run_id' = p_run_id::text
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

    update public.study_material_components
    set active_version_id = null
    where active_version_id = any (version_ids)
       or study_material_id = any (material_ids);

    delete from public.study_material_component_versions
    where id = any (version_ids);

    delete from public.study_material_components
    where study_material_id = any (material_ids);

    update public.study_materials
    set artifact_id = null
    where id = any (material_ids)
       or artifact_id = any (artifact_ids);

    delete from public.artifacts
    where id = any (artifact_ids);

    delete from public.study_materials
    where id = any (material_ids);

    delete from public.stage_runs
    where production_run_id = p_run_id;

    delete from public.production_runs
    where id = p_run_id;

    return query
    select 'sources'::text, so.name
    from storage.objects so
    where so.bucket_id = 'sources'
      and (
        so.name = any (storage_names)
        or so.name = any (knowledge_paths)
      )
      and not exists (
        select 1 from public.artifacts a where a.storage_path = so.name
      )
      and not exists (
        select 1 from public.study_materials sm where sm.final_html_path = so.name
      )
      and not exists (
        select 1
        from public.knowledge_projects kp
        where kp.notes_storage_path = so.name
      )
      and not exists (
        select 1
        from public.knowledge_item_plans plan
        where plan.visual->>'storage_path' = so.name
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
      )
    order by so.name;
    return;
  end if;

  select coalesce(array_agg(distinct entry_id), '{}')
  into wiki_ids
  from (
    select we.id as entry_id
    from public.wiki_entries we
    where we.origin->>'production_run_id' = p_run_id::text
      and we.created_at >= run_row.created_at
    union
    select inserted_id::uuid
    from public.stage_runs sr
    cross join lateral jsonb_array_elements_text(
      coalesce(sr.output->'inserted_ids', '[]'::jsonb)
    ) as inserted_id
    where sr.production_run_id = p_run_id
      and sr.stage_id = 'structure-wiki-notes'
      and inserted_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  ) created_wiki;

  select coalesce(array_agg(ns.id), '{}')
  into narration_ids
  from public.narration_segments ns
  join public.stage_runs sr
    on sr.production_run_id = p_run_id
   and sr.stage_id = 'generate-narration'
   and ns.source_id = nullif(sr.inputs->>'source_id', '')::uuid
   and ns.voice_id = sr.inputs->>'voice_id'
   and ns.model_id = sr.inputs->>'model_id'
  where not exists (
    select 1
    from public.artifacts a
    where a.production_run_id is distinct from p_run_id
      and a.source_id = ns.source_id
      and a.artifact_type = 'narration_audio'
      and a.manifest->>'voice_id' = ns.voice_id
      and a.manifest->>'model_id' = ns.model_id
  );

  select coalesce(array_agg(distinct path), '{}')
  into storage_names
  from (
    select a.storage_path as path
    from public.artifacts a
    where a.production_run_id = p_run_id
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
    where b.production_run_id = p_run_id
      and coalesce(att->>'storage_path', '') <> ''
      and not exists (
        select 1
        from public.sources s
        where s.storage_path = att->>'storage_path'
      )
      and not exists (
        select 1
        from public.knowledge_projects kp
        where kp.notes_storage_path = att->>'storage_path'
      )
    union
    select path
    from unnest(knowledge_paths) as path
    where coalesce(path, '') <> ''
  ) paths;

  if to_regclass('public.knowledge_item_plans') is not null then
    update public.knowledge_item_plans
    set assessment_id = null
    where assessment_id in (
      select id from public.flashcards where production_run_id = p_run_id
      union
      select id from public.quizzes where production_run_id = p_run_id
      union
      select id from public.scenarios where production_run_id = p_run_id
    );
  end if;

  foreach rel in array run_owned_tables loop
    if to_regclass('public.' || rel) is null then
      continue;
    end if;
    execute format(
      'delete from public.%I where production_run_id = $1',
      rel
    ) using p_run_id;
  end loop;

  delete from public.wiki_disputes
  where stage_run_id in (
    select id from public.stage_runs where production_run_id = p_run_id
  );

  if wiki_ids <> '{}'::uuid[] then
    update public.wiki_entries we
    set prerequisites = coalesce((
      select array_agg(prereq_id)
      from unnest(we.prerequisites) as prereq_id
      where prereq_id <> all (wiki_ids)
    ), '{}')
    where we.prerequisites && wiki_ids;

    delete from public.wiki_entries where id = any (wiki_ids);
  end if;

  delete from public.wiki_ingest_batches where production_run_id = p_run_id;
  delete from public.artifacts where production_run_id = p_run_id;

  if narration_ids <> '{}'::uuid[] then
    delete from public.narration_segments where id = any (narration_ids);
  end if;

  delete from public.stage_runs where production_run_id = p_run_id;
  delete from public.production_runs where id = p_run_id;

  return query
  select 'sources'::text, so.name
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
    )
    and not exists (
      select 1
      from public.knowledge_projects kp
      where kp.notes_storage_path = so.name
    )
    and not exists (
      select 1
      from public.knowledge_item_plans plan
      where plan.visual->>'storage_path' = so.name
    )
  order by so.name;
end
$purge$;

revoke execute on function public.purge_production_run(uuid) from public, anon, authenticated;
grant execute on function public.purge_production_run(uuid) to service_role;
