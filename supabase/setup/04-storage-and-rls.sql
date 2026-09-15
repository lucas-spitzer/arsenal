-- Foundry fresh setup: storage buckets and row-level security.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  (
    'sources',
    'sources',
    false,
    null,
    array[
      'application/pdf',
      'text/markdown',
      'application/epub+zip',
      'application/json',
      'audio/mpeg'
    ]
  )
on conflict (id) do nothing;

alter table public.workspaces enable row level security;
alter table public.stages enable row level security;
alter table public.workspace_stage_settings enable row level security;
alter table public.sources enable row level security;
alter table public.production_runs enable row level security;
alter table public.stage_runs enable row level security;
alter table public.ndr_segments enable row level security;
alter table public.document_chapters enable row level security;
alter table public.wiki_entries enable row level security;
alter table public.wiki_disputes enable row level security;
alter table public.wiki_ingest_batches enable row level security;
alter table public.artifacts enable row level security;
alter table public.narration_segments enable row level security;
alter table public.assessment_sets enable row level security;
alter table public.flashcards enable row level security;
alter table public.quizzes enable row level security;
alter table public.scenarios enable row level security;
alter table public.discussion_threads enable row level security;
alter table public.discussion_messages enable row level security;

revoke all on table public.workspaces from anon, authenticated;
revoke all on table public.stages from anon, authenticated;
revoke all on table public.workspace_stage_settings from anon, authenticated;
revoke all on table public.sources from anon, authenticated;
revoke all on table public.production_runs from anon, authenticated;
revoke all on table public.stage_runs from anon, authenticated;
revoke all on table public.ndr_segments from anon, authenticated;
revoke all on table public.document_chapters from anon, authenticated;
revoke all on table public.wiki_entries from anon, authenticated;
revoke all on table public.wiki_disputes from anon, authenticated;
revoke all on table public.wiki_ingest_batches from anon, authenticated;
revoke all on table public.artifacts from anon, authenticated;
revoke all on table public.narration_segments from anon, authenticated;
revoke all on table public.assessment_sets from anon, authenticated;
revoke all on table public.flashcards from anon, authenticated;
revoke all on table public.quizzes from anon, authenticated;
revoke all on table public.scenarios from anon, authenticated;
revoke all on table public.discussion_threads from anon, authenticated;
revoke all on table public.discussion_messages from anon, authenticated;

-- RAG helpers are service-role only (matches table-level revokes).
revoke execute on function public.match_ndr_segments(
  extensions.vector, uuid, double precision, integer, uuid[]
) from public, anon, authenticated;
revoke execute on function public.match_wiki_entries(
  extensions.vector, uuid, double precision, integer
) from public, anon, authenticated;

-- FastAPI uses the service role key for data access in V1.
