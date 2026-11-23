-- Atlas Points challenge tables for existing databases.
-- Idempotent. Fresh installs get the same shape from 02-schema.sql + 04-storage-and-rls.sql.
-- After applying, run wipe-quiz-results-for-atlas.sql to clear legacy batch scores.

create table if not exists public.question_progress (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  quiz_id uuid not null references public.quizzes (id) on delete cascade,
  correct_count integer not null default 0,
  incorrect_count integer not null default 0,
  mastered_at timestamptz,
  last_correct_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (user_id, quiz_id),
  constraint question_progress_counts_check
    check (correct_count >= 0 and incorrect_count >= 0)
);

create index if not exists question_progress_workspace_user_idx
on public.question_progress (workspace_id, user_id);

create table if not exists public.exam_attempts (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  exam_type text not null,
  subject_kind text,
  subject_id uuid,
  subject_name text,
  status text not null default 'in_progress',
  sequence_number integer not null default 1,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  question_count integer not null,
  correct_count integer not null default 0,
  points_earned integer not null default 0,
  quota_snapshot jsonb not null default '{}'::jsonb,
  questions jsonb not null default '[]'::jsonb,
  constraint exam_attempts_type_check
    check (exam_type in ('full_practice', 'subject', 'practice')),
  constraint exam_attempts_subject_kind_check
    check (subject_kind is null or subject_kind in ('source', 'lesson')),
  constraint exam_attempts_status_check
    check (status in ('in_progress', 'completed', 'abandoned')),
  constraint exam_attempts_counts_check
    check (
      question_count > 0
      and correct_count >= 0
      and correct_count <= question_count
      and points_earned >= 0
    )
);

create index if not exists exam_attempts_user_started_idx
on public.exam_attempts (workspace_id, user_id, started_at desc);

create unique index if not exists exam_attempts_sequence_uidx
on public.exam_attempts (workspace_id, user_id, exam_type, coalesce(subject_kind, ''), coalesce(subject_id::text, ''), sequence_number);

create table if not exists public.exam_answers (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid not null references public.exam_attempts (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  quiz_id uuid not null references public.quizzes (id) on delete cascade,
  question_index integer not null,
  question text not null,
  options jsonb not null,
  selected_index integer not null,
  is_correct boolean not null,
  points_awarded integer not null default 0,
  submitted_at timestamptz not null default now(),
  constraint exam_answers_selected_check check (selected_index >= 0),
  constraint exam_answers_points_check check (points_awarded >= 0),
  unique (attempt_id, quiz_id)
);

create index if not exists exam_answers_user_submitted_idx
on public.exam_answers (workspace_id, user_id, submitted_at desc);

create table if not exists public.score_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  quiz_id uuid not null references public.quizzes (id) on delete cascade,
  attempt_id uuid not null references public.exam_attempts (id) on delete cascade,
  answer_id uuid not null references public.exam_answers (id) on delete cascade,
  event_type text not null,
  points integer not null,
  created_at timestamptz not null default now(),
  constraint score_events_type_check
    check (event_type in ('first_correct', 'repeat_correct', 'mastery_bonus')),
  constraint score_events_points_check check (points > 0),
  unique (user_id, attempt_id, answer_id, event_type)
);

create index if not exists score_events_user_created_idx
on public.score_events (workspace_id, user_id, created_at desc);

create index if not exists score_events_workspace_created_idx
on public.score_events (workspace_id, created_at desc);

create table if not exists public.competition_settings (
  workspace_id uuid primary key references public.workspaces (id) on delete cascade,
  starts_at timestamptz not null default now(),
  -- Midnight America/New_York on 2026-12-01 = 05:00 UTC (EST).
  ends_at timestamptz not null default '2026-12-01 05:00:00+00',
  platoon_goal integer,
  student_access boolean not null default false,
  finalized_at timestamptz,
  final_standings jsonb,
  updated_at timestamptz not null default now(),
  constraint competition_settings_goal_check
    check (platoon_goal is null or platoon_goal > 0),
  constraint competition_settings_window_check
    check (ends_at > starts_at)
);

alter table public.question_progress enable row level security;
alter table public.exam_attempts enable row level security;
alter table public.exam_answers enable row level security;
alter table public.score_events enable row level security;
alter table public.competition_settings enable row level security;

revoke all on table public.question_progress from anon, authenticated;
revoke all on table public.exam_attempts from anon, authenticated;
revoke all on table public.exam_answers from anon, authenticated;
revoke all on table public.score_events from anon, authenticated;
revoke all on table public.competition_settings from anon, authenticated;
