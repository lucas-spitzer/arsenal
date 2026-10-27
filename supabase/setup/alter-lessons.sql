-- Existing databases only: adds the Academy ELO tab (TBS classes, their ELOs,
-- downloadable materials, and the lesson_chunks search index used by Discussions).
-- Kept apart from wiki_entries 'elo' rows built by Knowledge runs.
-- Idempotent.

create table if not exists public.lessons (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  title text not null,
  sort_order integer not null default 0,
  notes text,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint lessons_workspace_title_key unique (workspace_id, title)
);

create index if not exists lessons_workspace_order_idx
on public.lessons (workspace_id, sort_order);

drop trigger if exists lessons_set_updated_at on public.lessons;
create trigger lessons_set_updated_at
before update on public.lessons
for each row
execute function public.set_updated_at();

create table if not exists public.lesson_objectives (
  id uuid primary key default gen_random_uuid(),
  lesson_id uuid not null references public.lessons (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  position integer not null,
  text text not null,
  code text,
  is_async boolean not null default false,
  created_at timestamptz not null default now(),
  constraint lesson_objectives_lesson_position_key unique (lesson_id, position)
);

create index if not exists lesson_objectives_workspace_idx
on public.lesson_objectives (workspace_id);

create table if not exists public.lesson_resources (
  id uuid primary key default gen_random_uuid(),
  lesson_id uuid not null references public.lessons (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  kind text not null,
  label text not null,
  position integer not null default 0,
  url text,
  storage_path text,
  filename text,
  mime_type text,
  file_size_bytes bigint,
  index_status text not null default 'pending',
  index_error text,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint lesson_resources_kind_check check (kind in ('file', 'link')),
  constraint lesson_resources_shape_check check (
    (kind = 'file' and storage_path is not null and filename is not null)
    or (kind = 'link' and url is not null and url like 'https://%')
  ),
  constraint lesson_resources_index_status_check
    check (index_status in ('pending', 'indexing', 'ready', 'failed', 'skipped'))
);

create index if not exists lesson_resources_lesson_idx
on public.lesson_resources (lesson_id, position);

create index if not exists lesson_resources_workspace_idx
on public.lesson_resources (workspace_id);

drop trigger if exists lesson_resources_set_updated_at on public.lesson_resources;
create trigger lesson_resources_set_updated_at
before update on public.lesson_resources
for each row
execute function public.set_updated_at();

create table if not exists public.lesson_chunks (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  lesson_id uuid not null references public.lessons (id) on delete cascade,
  resource_id uuid references public.lesson_resources (id) on delete cascade,
  objective_id uuid references public.lesson_objectives (id) on delete cascade,
  kind text not null,
  sequence_index integer not null default 0,
  text text not null,
  locator jsonb not null default '{}',
  embedding extensions.vector(1536),
  created_at timestamptz not null default now(),
  constraint lesson_chunks_kind_check check (kind in ('objective', 'file_text'))
);

create index if not exists lesson_chunks_lesson_idx on public.lesson_chunks (lesson_id);
create index if not exists lesson_chunks_resource_idx on public.lesson_chunks (resource_id);
create index if not exists lesson_chunks_workspace_idx on public.lesson_chunks (workspace_id);
create index if not exists lesson_chunks_embedding_idx
on public.lesson_chunks using hnsw (embedding extensions.vector_cosine_ops);

alter table public.discussion_threads
  add column if not exists lesson_id uuid references public.lessons (id) on delete set null;

create or replace function public.match_lesson_chunks(
  query_embedding extensions.vector(1536),
  p_workspace_id uuid,
  match_threshold double precision default 0.3,
  match_count integer default 6,
  p_lesson_ids uuid[] default null
)
returns table (
  id uuid,
  lesson_id uuid,
  resource_id uuid,
  objective_id uuid,
  kind text,
  sequence_index integer,
  text text,
  locator jsonb,
  lesson_title text,
  resource_label text,
  filename text,
  similarity double precision
)
language sql
stable
set search_path = public, extensions
as $$
  select
    ch.id,
    ch.lesson_id,
    ch.resource_id,
    ch.objective_id,
    ch.kind,
    ch.sequence_index,
    ch.text,
    ch.locator,
    l.title as lesson_title,
    r.label as resource_label,
    r.filename,
    1 - (ch.embedding <=> query_embedding) as similarity
  from public.lesson_chunks ch
  join public.lessons l on l.id = ch.lesson_id
  left join public.lesson_resources r on r.id = ch.resource_id
  where ch.workspace_id = p_workspace_id
    and ch.embedding is not null
    and (p_lesson_ids is null or ch.lesson_id = any (p_lesson_ids))
    and 1 - (ch.embedding <=> query_embedding) >= match_threshold
  order by ch.embedding <=> query_embedding
  limit match_count;
$$;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'lesson-files',
  'lesson-files',
  false,
  null,
  array[
    'application/pdf',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'image/png',
    'image/jpeg'
  ]
)
on conflict (id) do nothing;

alter table public.lessons enable row level security;
alter table public.lesson_objectives enable row level security;
alter table public.lesson_resources enable row level security;
alter table public.lesson_chunks enable row level security;
revoke all on table public.lessons from anon, authenticated;
revoke all on table public.lesson_objectives from anon, authenticated;
revoke all on table public.lesson_resources from anon, authenticated;
revoke all on table public.lesson_chunks from anon, authenticated;

revoke execute on function public.match_lesson_chunks(
  extensions.vector, uuid, double precision, integer, uuid[]
) from public, anon, authenticated;
