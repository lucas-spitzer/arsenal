# One platoon library, two access roles

Arsenal serves one student platoon at The Basic School. The Academics officer produces the library in Foundry. Everyone else studies that same library in Academy. Tutor conversations stay with the student who started them.

`approved_users.role` is the access field. `admin` or `student`. The column used to default to `owner` and nothing checked it. Workspaces stay owned by the admin. Students read that workspace. They do not get a private copy of the books, wiki, artifacts, or assessments.
