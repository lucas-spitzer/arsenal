-- Seeds the Academics calendar for the week of Sun Oct 25 - Fri Oct 30, 2026
-- into the platoon workspace ("The Basic School").
-- Requires alter-calendar-events.sql (or a fresh 02-schema.sql). Safe to re-run:
-- rows that already exist (same workspace, date, and title) are skipped.

with platoon as (
  select id
  from public.workspaces
  where lower(trim(name)) = lower('The Basic School')
  limit 1
),
seed (event_date, kind, title, location, start_time, end_time) as (
  values
    (date '2026-10-25', 'deadline', 'Complete TCCC Quiz', null, null::time, null::time),
    (date '2026-10-25', 'deadline', 'Complete Sexual Assault Prevention Quiz', null, null, null),
    (date '2026-10-26', 'class', 'TCCC Class', 'CR-3', time '10:30', time '11:30'),
    (date '2026-10-27', 'prac_app', 'TCCC Prac App', 'Cannon Field', time '07:00', time '11:00'),
    (date '2026-10-28', 'evaluation', 'TCCC Evaluation', 'Cannon Field', time '07:00', time '11:00'),
    (date '2026-10-29', 'prac_app', 'TCCC Supplemental Evacuation Prac App', 'Cannon Field', time '07:00', time '11:00'),
    (date '2026-10-29', 'deadline', 'Print Intro to Marine Corps History Sheet', null, null, null),
    (date '2026-10-30', 'class', 'Intro to Anatomy and Biomechanics', 'CR-1', time '13:00', time '13:30'),
    (date '2026-10-30', 'class', 'Field and Garrison Diet', 'CR-1', time '13:30', time '14:30'),
    (date '2026-10-30', 'class', 'Intro to Marine Corps History', 'CR-1', time '14:30', time '16:30')
)
insert into public.calendar_events (workspace_id, event_date, kind, title, location, start_time, end_time)
select platoon.id, seed.event_date, seed.kind, seed.title, seed.location, seed.start_time, seed.end_time
from seed
cross join platoon
where not exists (
  select 1
  from public.calendar_events existing
  where existing.workspace_id = platoon.id
    and existing.event_date = seed.event_date
    and existing.title = seed.title
);
