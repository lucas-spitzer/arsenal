-- Foundry fresh setup: all application tables (final schema).

-- ---------------------------------------------------------------------------
-- Workspaces
-- ---------------------------------------------------------------------------

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  slug text not null,
  description text,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint workspaces_status_check
    check (status in ('active', 'archived')),
  constraint workspaces_slug_key unique (slug)
);

create index workspaces_owner_id_idx on public.workspaces (owner_id);
create unique index workspaces_name_lower_key on public.workspaces (lower(name));

create trigger workspaces_set_updated_at
before update on public.workspaces
for each row
execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Stages (versioned pipeline step definitions)
-- ---------------------------------------------------------------------------

create table public.stages (
  id uuid primary key default gen_random_uuid(),
  stage_id text not null,
  version text not null,
  module text not null,
  name text not null,
  description text,
  modalities text[] not null default '{}',
  input_schema jsonb not null default '{}',
  output_schema jsonb not null default '{}',
  prompts jsonb not null default '{}',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  constraint stages_module_check
    check (module in ('intellex', 'mathesys', 'qngen')),
  constraint stages_stage_id_version_key
    unique (stage_id, version)
);

create index stages_module_active_idx
on public.stages (module)
where is_active = true;

-- ---------------------------------------------------------------------------
-- Per-workspace LLM overrides for pipeline stage actions
-- ---------------------------------------------------------------------------

create table public.workspace_stage_settings (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  stage_action text not null,
  provider text not null,
  model text not null,
  reasoning_effort text,
  reasoning_tokens integer,
  voice_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint workspace_stage_settings_provider_check
    check (provider in ('openai', 'anthropic', 'speechify', 'elevenlabs')),
  constraint workspace_stage_settings_reasoning_tokens_check
    check (reasoning_tokens is null or reasoning_tokens > 0),
  constraint workspace_stage_settings_workspace_action_key
    unique (workspace_id, stage_action)
);

create index workspace_stage_settings_workspace_id_idx
on public.workspace_stage_settings (workspace_id);

create trigger workspace_stage_settings_set_updated_at
before update on public.workspace_stage_settings
for each row
execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Sources (uploaded files)
-- ---------------------------------------------------------------------------

create table public.sources (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  filename text not null,
  slug text not null,
  mime_type text not null,
  storage_path text not null,
  file_hash text not null,
  file_size_bytes bigint not null,
  source_metadata jsonb not null default '{}',
  status text not null default 'stored',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint sources_status_check
    check (status in ('stored', 'processing', 'ready', 'failed')),
  constraint sources_workspace_file_hash_key
    unique (workspace_id, file_hash),
  constraint sources_workspace_slug_key
    unique (workspace_id, slug)
);

create index sources_workspace_id_idx on public.sources (workspace_id);
create index sources_owner_id_idx on public.sources (owner_id);

create trigger sources_set_updated_at
before update on public.sources
for each row
execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Production runs (pipeline orchestration)
-- ---------------------------------------------------------------------------

create table public.production_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  source_ids uuid[] not null default '{}',
  target_artifacts text[] not null default '{}',
  pipeline jsonb not null default '[]',
  status text not null default 'queued',
  error text,
  cost_usd numeric(12, 6) not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint production_runs_status_check
    check (status in ('queued', 'running', 'completed', 'failed', 'cancelled'))
);

create index production_runs_workspace_id_idx on public.production_runs (workspace_id);
create index production_runs_status_idx on public.production_runs (status);
create index production_runs_cost_usd_idx on public.production_runs (cost_usd);

create trigger production_runs_set_updated_at
before update on public.production_runs
for each row
execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Stage runs (execution + immutable output)
-- ---------------------------------------------------------------------------

create table public.stage_runs (
  id uuid primary key default gen_random_uuid(),
  production_run_id uuid references public.production_runs (id) on delete set null,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  stage_id text not null,
  stage_version text not null,
  module text not null,
  status text not null default 'queued',
  inputs jsonb not null default '{}',
  output jsonb,
  promoted jsonb not null default '{}',
  model text,
  token_usage jsonb not null default '{}',
  api_usage jsonb not null default '{}',
  cost_usd numeric(12, 6) not null default 0,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  constraint stage_runs_module_check
    check (module in ('intellex', 'mathesys', 'qngen')),
  constraint stage_runs_status_check
    check (status in ('queued', 'running', 'completed', 'failed', 'cancelled')),
  constraint stage_runs_stage_fk
    foreign key (stage_id, stage_version)
    references public.stages (stage_id, version)
);

create index stage_runs_production_run_id_idx on public.stage_runs (production_run_id);
create index stage_runs_workspace_id_idx on public.stage_runs (workspace_id);
create index stage_runs_status_idx on public.stage_runs (status);
create index stage_runs_cost_usd_idx on public.stage_runs (cost_usd);

-- ---------------------------------------------------------------------------
-- NDR segments (parsed and chunked source content)
-- text = plain (LLM / embeddings / narration); md = inline markdown for Reader
-- ---------------------------------------------------------------------------

create table public.ndr_segments (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  sequence_index integer not null,
  kind text not null,
  text text not null,
  md text,
  locator jsonb not null default '{}',
  embedding extensions.vector(1536),
  embedded_at timestamptz,
  created_at timestamptz not null default now(),
  constraint ndr_segments_kind_check
    check (kind in ('heading', 'paragraph', 'list_item', 'table', 'caption')),
  constraint ndr_segments_source_sequence_key
    unique (source_id, sequence_index)
);

create index ndr_segments_source_id_idx on public.ndr_segments (source_id);
create index ndr_segments_workspace_id_idx on public.ndr_segments (workspace_id);
create index ndr_segments_source_sequence_idx
on public.ndr_segments (source_id, sequence_index);
create index ndr_segments_embedding_idx
on public.ndr_segments using hnsw (embedding extensions.vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Document chapters (persisted chapter/section segmentation)
-- ---------------------------------------------------------------------------

create table public.document_chapters (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  sequence_index integer not null,
  title text not null,
  level integer not null default 1,
  segment_ids uuid[] not null,
  sections jsonb not null default '[]',
  created_at timestamptz not null default now(),
  constraint document_chapters_source_sequence_key
    unique (source_id, sequence_index)
);

create index document_chapters_source_id_idx on public.document_chapters (source_id);
create index document_chapters_workspace_id_idx on public.document_chapters (workspace_id);

-- ---------------------------------------------------------------------------
-- Wiki entries and dispute logging
-- ---------------------------------------------------------------------------

create table public.wiki_entries (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  preferred_label text not null,
  canonical_slug text not null,
  definition text not null,
  pronunciation text,
  aliases text[] not null default '{}',
  prerequisites uuid[] not null default '{}',
  importance text not null default 'supporting',
  status text not null default 'canonical',
  entry_kind text not null default 'concept',
  evidence jsonb not null default '[]',
  origin jsonb not null default '{}',
  confidence double precision,
  selection_score double precision,
  embedding extensions.vector(1536),
  embedded_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint wiki_entries_importance_check
    check (importance in ('essential', 'supporting', 'contextual')),
  constraint wiki_entries_status_check
    check (status in ('candidate', 'canonical', 'disputed', 'deprecated', 'rejected')),
  constraint wiki_entries_entry_kind_check
    check (entry_kind in ('term', 'concept', 'insight')),
  constraint wiki_entries_workspace_slug_key
    unique (workspace_id, canonical_slug)
);

create index wiki_entries_workspace_id_idx on public.wiki_entries (workspace_id);
create index wiki_entries_status_idx on public.wiki_entries (workspace_id, status);
create index wiki_entries_workspace_status_score_idx
on public.wiki_entries (workspace_id, status, selection_score);
create index wiki_entries_embedding_idx
on public.wiki_entries using hnsw (embedding extensions.vector_cosine_ops);

create trigger wiki_entries_set_updated_at
before update on public.wiki_entries
for each row
execute function public.set_updated_at();

create table public.wiki_disputes (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  wiki_entry_id uuid references public.wiki_entries (id) on delete set null,
  term_label text not null,
  existing_definition text,
  proposed_definition text not null,
  stage_run_id uuid references public.stage_runs (id) on delete set null,
  source_id uuid references public.sources (id) on delete set null,
  status text not null default 'open',
  created_at timestamptz not null default now(),
  constraint wiki_disputes_status_check
    check (status in ('open', 'resolved'))
);

create index wiki_disputes_workspace_id_idx on public.wiki_disputes (workspace_id);
create index wiki_disputes_wiki_entry_id_idx on public.wiki_disputes (wiki_entry_id);

-- ---------------------------------------------------------------------------
-- Wiki ingest batches (manual authoring drafts; never provisional wiki rows)
-- ---------------------------------------------------------------------------

create table public.wiki_ingest_batches (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_id uuid references public.sources (id) on delete set null,
  production_run_id uuid references public.production_runs (id) on delete set null,
  title text not null,
  -- Empty while status = transcribing (file ingest); filled after transcription
  -- or immediately for paste-notes batches.
  raw_notes text not null default '',
  chapter_hint text,
  chapter jsonb,
  status text not null default 'draft',
  entries jsonb not null default '[]',
  unparsed_fragments jsonb not null default '[]',
  -- Uploaded note files: [{order, filename, mime_type, storage_path, byte_size}]
  attachments jsonb not null default '[]',
  transcription_error text,
  model text,
  cost_usd numeric(12, 6),
  committed_entry_ids uuid[] not null default '{}',
  committed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint wiki_ingest_batches_status_check
    check (
      status in (
        'transcribing',
        'transcribed',
        'structuring',
        'draft',
        'committed',
        'discarded',
        'failed'
      )
    )
);

create index wiki_ingest_batches_workspace_id_idx
on public.wiki_ingest_batches (workspace_id);
create index wiki_ingest_batches_source_id_idx
on public.wiki_ingest_batches (source_id);
create index wiki_ingest_batches_production_run_id_idx
on public.wiki_ingest_batches (production_run_id);
create index wiki_ingest_batches_status_idx
on public.wiki_ingest_batches (workspace_id, status);

create trigger wiki_ingest_batches_set_updated_at
before update on public.wiki_ingest_batches
for each row
execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Generated artifacts
-- ---------------------------------------------------------------------------

create table public.artifacts (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_id uuid references public.sources (id) on delete set null,
  production_run_id uuid references public.production_runs (id) on delete set null,
  artifact_type text not null,
  format text not null,
  filename text not null,
  storage_path text not null,
  file_size_bytes bigint not null default 0,
  manifest jsonb not null default '{}',
  origin jsonb not null default '{}',
  created_at timestamptz not null default now(),
  constraint artifacts_type_check
    check (
      artifact_type in (
        'electronic_book',
        'narration_audio',
        'wiki_json',
        'study_sheet'
      )
    )
);

create index artifacts_workspace_id_idx on public.artifacts (workspace_id);
create index artifacts_source_id_idx on public.artifacts (source_id);
create index artifacts_production_run_id_idx on public.artifacts (production_run_id);

-- ---------------------------------------------------------------------------
-- Narration segments (per-paragraph audio + word timings for the Reader)
-- ---------------------------------------------------------------------------

create table public.narration_segments (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_id uuid not null references public.sources (id) on delete cascade,
  chapter_id uuid references public.document_chapters (id) on delete set null,
  segment_id uuid not null references public.ndr_segments (id) on delete cascade,
  voice_id text not null,
  model_id text not null,
  audio_path text not null,
  duration_seconds double precision not null default 0,
  words jsonb not null default '[]',
  request_id text,
  character_count integer not null default 0,
  created_at timestamptz not null default now(),
  constraint narration_segments_segment_voice_key
    unique (segment_id, voice_id)
);

create index narration_segments_source_id_idx
on public.narration_segments (source_id);
create index narration_segments_workspace_id_idx
on public.narration_segments (workspace_id);

-- ---------------------------------------------------------------------------
-- Assessment sets and promoted QnGen entities
-- ---------------------------------------------------------------------------

create table public.assessment_sets (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_id uuid references public.sources (id) on delete set null,
  production_run_id uuid references public.production_runs (id) on delete set null,
  stage_run_id uuid references public.stage_runs (id) on delete set null,
  title text not null,
  learning_goal text,
  assessment_types text[] not null default '{}',
  items jsonb not null default '[]',
  origin jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index assessment_sets_workspace_id_idx on public.assessment_sets (workspace_id);
create index assessment_sets_source_id_idx on public.assessment_sets (source_id);
create index assessment_sets_production_run_id_idx on public.assessment_sets (production_run_id);

create table public.flashcards (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_id uuid references public.sources (id) on delete set null,
  production_run_id uuid references public.production_runs (id) on delete set null,
  stage_run_id uuid references public.stage_runs (id) on delete set null,
  assessment_set_id uuid references public.assessment_sets (id) on delete set null,
  item_id uuid,
  subtype text not null default 'basic',
  front text not null,
  back text not null,
  difficulty text not null default 'medium',
  tags text[] not null default '{}',
  citations jsonb not null default '[]',
  origin jsonb not null default '{}',
  created_at timestamptz not null default now(),
  constraint flashcards_difficulty_check
    check (difficulty in ('easy', 'medium', 'hard'))
);

create index flashcards_workspace_id_idx on public.flashcards (workspace_id);
create index flashcards_source_id_idx on public.flashcards (source_id);
create index flashcards_assessment_set_id_idx on public.flashcards (assessment_set_id);

create table public.quizzes (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_id uuid references public.sources (id) on delete set null,
  production_run_id uuid references public.production_runs (id) on delete set null,
  stage_run_id uuid references public.stage_runs (id) on delete set null,
  assessment_set_id uuid references public.assessment_sets (id) on delete set null,
  item_id uuid,
  subtype text,
  question text not null,
  question_type text not null default 'multiple_choice',
  options jsonb not null default '[]',
  correct_answer text not null,
  explanation text,
  difficulty text not null default 'medium',
  citations jsonb not null default '[]',
  origin jsonb not null default '{}',
  created_at timestamptz not null default now(),
  constraint quizzes_question_type_check
    check (
      question_type in (
        'multiple_choice',
        'true_false',
        'short_answer',
        'multiple_select',
        'true_false_correction',
        'matching',
        'ordering',
        'assertion_reason',
        'compare_contrast'
      )
    ),
  constraint quizzes_difficulty_check
    check (difficulty in ('easy', 'medium', 'hard'))
);

create index quizzes_workspace_id_idx on public.quizzes (workspace_id);
create index quizzes_source_id_idx on public.quizzes (source_id);
create index quizzes_assessment_set_id_idx on public.quizzes (assessment_set_id);

create table public.scenarios (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_id uuid references public.sources (id) on delete set null,
  production_run_id uuid references public.production_runs (id) on delete set null,
  stage_run_id uuid references public.stage_runs (id) on delete set null,
  assessment_set_id uuid references public.assessment_sets (id) on delete set null,
  item_id uuid,
  subtype text not null default 'decision_prompt',
  title text not null,
  prompt text not null,
  context text,
  evaluation_criteria jsonb not null default '[]',
  rubric jsonb,
  difficulty text not null default 'medium',
  citations jsonb not null default '[]',
  origin jsonb not null default '{}',
  created_at timestamptz not null default now(),
  constraint scenarios_difficulty_check
    check (difficulty in ('easy', 'medium', 'hard'))
);

create index scenarios_workspace_id_idx on public.scenarios (workspace_id);
create index scenarios_source_id_idx on public.scenarios (source_id);
create index scenarios_assessment_set_id_idx on public.scenarios (assessment_set_id);

-- ---------------------------------------------------------------------------
-- Discussion threads (persisted assistant conversations)
-- ---------------------------------------------------------------------------

create table public.discussion_threads (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  title text not null,
  submode text not null default 'socratic',
  source_id uuid references public.sources (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint discussion_threads_submode_check
    check (submode in ('socratic', 'euclidean'))
);

create index discussion_threads_workspace_id_idx
on public.discussion_threads (workspace_id);

create trigger discussion_threads_set_updated_at
before update on public.discussion_threads
for each row
execute function public.set_updated_at();

create table public.discussion_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.discussion_threads (id) on delete cascade,
  role text not null,
  content text not null,
  citations jsonb not null default '[]',
  created_at timestamptz not null default now(),
  constraint discussion_messages_role_check
    check (role in ('user', 'assistant'))
);

create index discussion_messages_thread_id_idx
on public.discussion_messages (thread_id, created_at);

-- ---------------------------------------------------------------------------
-- RAG match helpers (service role only; tenancy via p_workspace_id)
-- ---------------------------------------------------------------------------

create or replace function public.match_ndr_segments(
  query_embedding extensions.vector(1536),
  p_workspace_id uuid,
  match_threshold double precision default 0.3,
  match_count integer default 8,
  p_source_ids uuid[] default null
)
returns table (
  id uuid,
  source_id uuid,
  sequence_index integer,
  kind text,
  text text,
  locator jsonb,
  chapter_title text,
  chapter_sequence integer,
  similarity double precision
)
language sql
stable
set search_path = public, extensions
as $$
  select
    s.id,
    s.source_id,
    s.sequence_index,
    s.kind,
    s.text,
    s.locator,
    c.title as chapter_title,
    c.sequence_index as chapter_sequence,
    1 - (s.embedding <=> query_embedding) as similarity
  from public.ndr_segments s
  left join lateral (
    select dc.title, dc.sequence_index
    from public.document_chapters dc
    where dc.source_id = s.source_id
      and s.id = any (dc.segment_ids)
    limit 1
  ) c on true
  where s.workspace_id = p_workspace_id
    and s.embedding is not null
    and (p_source_ids is null or s.source_id = any (p_source_ids))
    and 1 - (s.embedding <=> query_embedding) >= match_threshold
  order by s.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function public.match_wiki_entries(
  query_embedding extensions.vector(1536),
  p_workspace_id uuid,
  match_threshold double precision default 0.3,
  match_count integer default 6
)
returns table (
  id uuid,
  preferred_label text,
  canonical_slug text,
  definition text,
  importance text,
  similarity double precision
)
language sql
stable
set search_path = public, extensions
as $$
  select
    w.id,
    w.preferred_label,
    w.canonical_slug,
    w.definition,
    w.importance,
    1 - (w.embedding <=> query_embedding) as similarity
  from public.wiki_entries w
  where w.workspace_id = p_workspace_id
    and w.embedding is not null
    and w.status = 'canonical'
    and 1 - (w.embedding <=> query_embedding) >= match_threshold
  order by w.embedding <=> query_embedding
  limit match_count;
$$;
