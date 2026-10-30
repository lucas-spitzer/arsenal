-- Allow abbreviation wiki entries written by a Knowledge question pack.
-- Fresh installs already include this check in supabase/setup/02-schema.sql.

alter table public.wiki_entries
  drop constraint wiki_entries_entry_kind_check;

alter table public.wiki_entries
  add constraint wiki_entries_entry_kind_check
  check (entry_kind in ('term', 'list', 'elo', 'abbreviation'));
