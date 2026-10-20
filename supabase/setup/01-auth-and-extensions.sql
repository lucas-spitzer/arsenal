-- Foundry fresh setup: extensions, helpers, and auth allowlist.

create extension if not exists citext;
create extension if not exists pgcrypto;
-- RAG embeddings (text-embedding-3-small, 1536 dims). Kept in the extensions
-- schema so it does not collide with the public API surface.
create extension if not exists vector with schema extensions;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table public.approved_users (
  id uuid primary key default gen_random_uuid(),
  email citext unique not null,
  role text not null default 'student',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  constraint approved_users_role_check
    check (role in ('admin', 'student'))
);

-- Replace with your Google account email before signing in.
-- admin: Foundry and Academy. student: Academy only.
insert into public.approved_users (email, role, is_active)
values ('example@email.com', 'admin', true)
on conflict (email)
do update set is_active = true, role = excluded.role;

alter table public.approved_users enable row level security;

revoke all on table public.approved_users from anon, authenticated;
