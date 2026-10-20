-- Existing databases: constrain approved_users.role and give each
-- discussion thread a student. Fresh installs from 01–04 already include this.

update public.approved_users
set role = 'admin'
where role = 'owner';

alter table public.approved_users
  drop constraint if exists approved_users_role_check;

alter table public.approved_users
  add constraint approved_users_role_check
  check (role in ('admin', 'student'));

alter table public.approved_users
  alter column role set default 'student';

alter table public.discussion_threads
  add column if not exists user_id uuid references auth.users (id) on delete cascade;

update public.discussion_threads as thread
set user_id = workspace.owner_id
from public.workspaces as workspace
where thread.workspace_id = workspace.id
  and thread.user_id is null;

alter table public.discussion_threads
  alter column user_id set not null;

create index if not exists discussion_threads_user_id_idx
on public.discussion_threads (workspace_id, user_id);
