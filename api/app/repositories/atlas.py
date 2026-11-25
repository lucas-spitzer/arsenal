from typing import Any

from app.services.supabase_rest import SupabaseRestClient


class AtlasRepository:
    def __init__(self, db: SupabaseRestClient) -> None:
        self.db = db

    async def get_progress(self, user_id: str, quiz_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "question_progress",
            filters={"user_id": f"eq.{user_id}", "quiz_id": f"eq.{quiz_id}"},
        )

    async def list_progress_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "question_progress",
            filters={"workspace_id": f"eq.{workspace_id}", "user_id": f"eq.{user_id}"},
        )

    async def list_progress_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "question_progress",
            filters={"workspace_id": f"eq.{workspace_id}"},
        )

    async def upsert_progress(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.request(
            "POST",
            "question_progress",
            json_body=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if isinstance(rows, list) and rows:
            return rows[0]
        if isinstance(rows, dict):
            return rows
        existing = await self.get_progress(str(payload["user_id"]), str(payload["quiz_id"]))
        if existing:
            return existing
        raise RuntimeError("Could not upsert question progress.")

    async def insert_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("exam_attempts", payload)
        return rows[0]

    async def get_attempt(self, attempt_id: str, workspace_id: str, user_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "exam_attempts",
            filters={
                "id": f"eq.{attempt_id}",
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
            },
        )

    async def update_attempt(self, attempt_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.update(
            "exam_attempts",
            filters={"id": f"eq.{attempt_id}"},
            payload=payload,
        )
        return rows[0]

    async def list_attempts_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "exam_attempts",
            filters={"workspace_id": f"eq.{workspace_id}", "user_id": f"eq.{user_id}"},
            order="started_at.desc",
        )

    async def list_attempts_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "exam_attempts",
            filters={"workspace_id": f"eq.{workspace_id}"},
            order="started_at.desc",
        )

    async def next_sequence(
        self,
        workspace_id: str,
        user_id: str,
        exam_type: str,
        subject_kind: str | None,
        subject_id: str | None,
    ) -> int:
        filters: dict[str, str] = {
            "workspace_id": f"eq.{workspace_id}",
            "user_id": f"eq.{user_id}",
            "exam_type": f"eq.{exam_type}",
        }
        if subject_kind:
            filters["subject_kind"] = f"eq.{subject_kind}"
        else:
            filters["subject_kind"] = "is.null"
        if subject_id:
            filters["subject_id"] = f"eq.{subject_id}"
        else:
            filters["subject_id"] = "is.null"
        rows = await self.db.select_many(
            "exam_attempts",
            filters=filters,
            columns="sequence_number",
            order="sequence_number.desc",
            limit=1,
        )
        if not rows:
            return 1
        return int(rows[0]["sequence_number"]) + 1

    async def insert_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.insert("exam_answers", payload)
        return rows[0]

    async def get_answer(self, attempt_id: str, quiz_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "exam_answers",
            filters={"attempt_id": f"eq.{attempt_id}", "quiz_id": f"eq.{quiz_id}"},
        )

    async def list_answers_for_attempt(self, attempt_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "exam_answers",
            filters={"attempt_id": f"eq.{attempt_id}"},
            order="question_index.asc",
        )

    async def list_answers_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "exam_answers",
            filters={"workspace_id": f"eq.{workspace_id}", "user_id": f"eq.{user_id}"},
            order="submitted_at.desc",
        )

    async def list_answers_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "exam_answers",
            filters={"workspace_id": f"eq.{workspace_id}"},
        )

    async def insert_score_events(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        return await self.db.insert("score_events", rows)

    async def list_score_events_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "score_events",
            filters={"workspace_id": f"eq.{workspace_id}", "user_id": f"eq.{user_id}"},
            order="created_at.desc",
        )

    async def list_score_points_for_user(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "score_events",
            filters={"workspace_id": f"eq.{workspace_id}", "user_id": f"eq.{user_id}"},
            columns="points",
        )

    async def list_score_events_for_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "score_events",
            filters={"workspace_id": f"eq.{workspace_id}"},
        )

    async def get_competition(self, workspace_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "competition_settings",
            filters={"workspace_id": f"eq.{workspace_id}"},
        )

    async def upsert_competition(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.request(
            "POST",
            "competition_settings",
            json_body=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if isinstance(rows, list) and rows:
            return rows[0]
        if isinstance(rows, dict):
            return rows
        existing = await self.get_competition(str(payload["workspace_id"]))
        if existing:
            return existing
        raise RuntimeError("Could not upsert competition settings.")

    async def update_competition(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.update(
            "competition_settings",
            filters={"workspace_id": f"eq.{workspace_id}"},
            payload=payload,
        )
        return rows[0]

    async def finalize_competition_if_open(
        self,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = await self.db.update(
            "competition_settings",
            filters={"workspace_id": f"eq.{workspace_id}", "finalized_at": "is.null"},
            payload=payload,
        )
        return rows[0] if rows else None

    async def list_approved_roster(self) -> list[dict[str, Any]]:
        return await self.db.select_many(
            "approved_users",
            filters={"is_active": "eq.true"},
            columns="email,role,name,rank",
            order="name.asc.nullslast",
        )

    async def list_auth_users_by_emails(self, emails: list[str]) -> list[dict[str, Any]]:
        """Map roster emails to auth.users via a view-free REST lookup is unavailable.

        Callers should use the Auth Admin API when needed. This helper is a stub
        kept for repository symmetry; prefer SupabaseService for user id resolution.
        """
        del emails
        return []
