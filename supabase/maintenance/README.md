# Local operator SQL

These scripts stay off the public repository so they do not leak confidential information about the platform and its plans. That includes every `.sql` file in this folder, plus:

- `supabase/setup/seed-*.sql`
- `supabase/setup/05-purge-production-run.sql`

They stay on the machine that already has them. Git tracks this README only.

`git add -f` would publish them again. Do not use it.

A new clone of this repository will not contain these scripts. Copy them from the machine that has them if you need them on another computer.

Older commits on the public GitHub repository still contain the previous files. This ignore rule does not erase history.
