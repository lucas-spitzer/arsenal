-- Widens calendar event kinds with "schedule" and adds per-student task checks.
-- Safe to re-run. The API uses the service role; anon and authenticated stay revoked.

alter table public.calendar_events drop constraint if exists calendar_events_kind_check;

alter table public.calendar_events
  add constraint calendar_events_kind_check
  check (kind in ('deadline', 'class', 'prac_app', 'evaluation', 'schedule'));

create table if not exists public.calendar_task_completions (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  event_id uuid not null references public.calendar_events (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  completed_at timestamptz not null default now(),
  constraint calendar_task_completions_event_user_key unique (event_id, user_id)
);

create index if not exists calendar_task_completions_user_idx
  on public.calendar_task_completions (workspace_id, user_id);

alter table public.calendar_task_completions enable row level security;

revoke all on table public.calendar_task_completions from anon, authenticated;
