-- Existing databases only: adds the Academics calendar (deadlines, classes, prac apps).
-- Idempotent.

create table if not exists public.calendar_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  title text not null,
  kind text not null default 'class',
  event_date date not null,
  start_time time,
  end_time time,
  location text,
  notes text,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint calendar_events_kind_check
    check (kind in ('deadline', 'class', 'prac_app', 'evaluation')),
  constraint calendar_events_time_order_check
    check (start_time is null or end_time is null or end_time >= start_time)
);

create index if not exists calendar_events_workspace_date_idx
on public.calendar_events (workspace_id, event_date);

drop trigger if exists calendar_events_set_updated_at on public.calendar_events;
create trigger calendar_events_set_updated_at
before update on public.calendar_events
for each row
execute function public.set_updated_at();

alter table public.calendar_events enable row level security;
revoke all on table public.calendar_events from anon, authenticated;
