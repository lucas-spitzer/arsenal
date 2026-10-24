-- Existing databases: allow the TBS discussion instruction.
-- Fresh installs from 01–04 already include this.

alter table public.discussion_threads
  drop constraint if exists discussion_threads_submode_check;

alter table public.discussion_threads
  add constraint discussion_threads_submode_check
  check (submode in ('socratic', 'euclidean', 'tbs'));

alter table public.discussion_threads
  alter column submode set default 'tbs';
