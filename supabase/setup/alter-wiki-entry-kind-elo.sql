-- Existing databases: allow Enabling Learning Objectives on wiki entries.
-- Fresh installs from 01–04 already include this.

alter table public.wiki_entries
  drop constraint if exists wiki_entries_entry_kind_check;

alter table public.wiki_entries
  add constraint wiki_entries_entry_kind_check
  check (entry_kind in ('term', 'list', 'elo'));
