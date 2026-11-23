"""Atlas Points challenge orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.access import is_admin
from app.config import Settings
from app.knowledge.answer_pool import ShownAnswerError, grade_shown_answer
from app.models.atlas import (
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    AtlasAccessResponse,
    AtlasMeResponse,
    CompetitionSettingsResponse,
    CompetitionSettingsUpdate,
    ExamAttemptResponse,
    ExamQuestion,
    ExamStartRequest,
    LeaderboardEntry,
    LeaderboardResponse,
    PlatoonDashboardResponse,
    PointsAwarded,
    PracticeAnswerRequest,
    SubjectBreakdown,
)
from app.models.auth import CurrentUser
from app.repositories.assessments import AssessmentRepository
from app.repositories.atlas import AtlasRepository
from app.repositories.lessons import LessonRepository
from app.repositories.sources import SourceRepository
from app.services.atlas_exams import (
    ExamAssemblyError,
    assemble_full_practice,
    assemble_subject_exam,
    source_label,
)
from app.services.atlas_scoring import (
    accuracy_from_counts,
    apply_correct_progress,
    apply_incorrect_progress,
    sort_leaderboard_rows,
    sum_points,
)
from app.services.supabase_rest import SupabaseRestClient


class AtlasError(Exception):
    def __init__(self, detail: str, *, status_code: int = 422) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


DEFAULT_ENDS_AT = "2026-12-01T05:00:00+00:00"


class AtlasService:
    def __init__(
        self,
        *,
        atlas: AtlasRepository,
        assessments: AssessmentRepository,
        sources: SourceRepository,
        lessons: LessonRepository,
        db: SupabaseRestClient,
        settings: Settings,
    ) -> None:
        self.atlas = atlas
        self.assessments = assessments
        self.sources = sources
        self.lessons = lessons
        self.db = db
        self.settings = settings

    async def ensure_access(self, user: CurrentUser, workspace_id: str) -> dict[str, Any]:
        competition = await self.ensure_competition(workspace_id)
        if is_admin(user) or bool(competition.get("student_access")):
            return competition
        raise AtlasError("Atlas Points is not open to students yet.", status_code=403)

    async def ensure_competition(self, workspace_id: str) -> dict[str, Any]:
        existing = await self.atlas.get_competition(workspace_id)
        if existing:
            return existing
        now = datetime.now(UTC).isoformat()
        return await self.atlas.upsert_competition(
            {
                "workspace_id": workspace_id,
                "starts_at": now,
                "ends_at": DEFAULT_ENDS_AT,
                "platoon_goal": None,
                "student_access": False,
                "finalized_at": None,
                "final_standings": None,
                "updated_at": now,
            }
        )

    async def list_all_quizzes(self, workspace_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        page = 200
        while True:
            batch = await self.assessments.list_quizzes(workspace_id, limit=page, offset=offset)
            rows.extend(batch)
            if len(batch) < page:
                break
            offset += page
        return rows

    async def start_exam(
        self,
        *,
        user: CurrentUser,
        workspace_id: str,
        owner_id: str,
        payload: ExamStartRequest,
    ) -> ExamAttemptResponse:
        await self.ensure_access(user, workspace_id)
        quizzes = await self.list_all_quizzes(workspace_id)
        sources = await self.sources.list_for_workspace(workspace_id, owner_id)
        lesson_rows = await self.lessons.list_with_children(workspace_id)
        try:
            if payload.exam_type == "full_practice":
                questions, snapshot = assemble_full_practice(quizzes, sources, lesson_rows)
                subject_kind = None
                subject_id = None
                subject_name = None
            else:
                if payload.subject_kind not in {"source", "lesson"} or not payload.subject_id:
                    raise AtlasError("Subject exams need a source or lesson.")
                subject_kind = payload.subject_kind
                subject_id = payload.subject_id
                if subject_kind == "source":
                    source = next((row for row in sources if str(row["id"]) == subject_id), None)
                    if not source:
                        raise AtlasError("That source is not in this workspace.", status_code=404)
                    subject_name = source_label(source)
                else:
                    lesson = next((row for row in lesson_rows if str(row["id"]) == subject_id), None)
                    if not lesson:
                        raise AtlasError("That class is not in this workspace.", status_code=404)
                    subject_name = str(lesson.get("title") or "Class")
                questions, snapshot = assemble_subject_exam(
                    quizzes,
                    subject_kind=subject_kind,
                    subject_id=subject_id,
                    subject_name=subject_name,
                )
        except ExamAssemblyError as exc:
            raise AtlasError(exc.detail) from exc

        sequence = await self.atlas.next_sequence(
            workspace_id,
            user.id,
            payload.exam_type,
            subject_kind,
            subject_id,
        )
        row = await self.atlas.insert_attempt(
            {
                "workspace_id": workspace_id,
                "user_id": user.id,
                "exam_type": payload.exam_type,
                "subject_kind": subject_kind,
                "subject_id": subject_id,
                "subject_name": subject_name,
                "status": "in_progress",
                "sequence_number": sequence,
                "question_count": len(questions),
                "correct_count": 0,
                "points_earned": 0,
                "quota_snapshot": snapshot,
                "questions": questions,
            }
        )
        return self._attempt_response(row, [])

    async def submit_exam_answer(
        self,
        *,
        user: CurrentUser,
        workspace_id: str,
        attempt_id: str,
        payload: AnswerSubmitRequest,
    ) -> AnswerSubmitResponse:
        await self.ensure_access(user, workspace_id)
        attempt = await self.atlas.get_attempt(attempt_id, workspace_id, user.id)
        if not attempt:
            raise AtlasError("Exam attempt not found.", status_code=404)
        if attempt.get("status") != "in_progress":
            raise AtlasError("That exam is already finished.")
        return await self._grade_and_record(
            user=user,
            workspace_id=workspace_id,
            attempt=attempt,
            payload=payload,
            allow_any_quiz=False,
        )

    async def complete_exam(
        self,
        *,
        user: CurrentUser,
        workspace_id: str,
        attempt_id: str,
    ) -> ExamAttemptResponse:
        await self.ensure_access(user, workspace_id)
        attempt = await self.atlas.get_attempt(attempt_id, workspace_id, user.id)
        if not attempt:
            raise AtlasError("Exam attempt not found.", status_code=404)
        answers = await self.atlas.list_answers_for_attempt(attempt_id)
        if attempt.get("status") == "in_progress":
            attempt = await self.atlas.update_attempt(
                attempt_id,
                {
                    "status": "completed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "correct_count": sum(1 for row in answers if row.get("is_correct")),
                    "points_earned": sum(int(row.get("points_awarded") or 0) for row in answers),
                },
            )
        return self._attempt_response(attempt, answers)

    async def submit_practice_answer(
        self,
        *,
        user: CurrentUser,
        workspace_id: str,
        payload: PracticeAnswerRequest,
    ) -> AnswerSubmitResponse:
        await self.ensure_access(user, workspace_id)
        sequence = await self.atlas.next_sequence(workspace_id, user.id, "practice", None, None)
        question = {
            "quiz_id": payload.quiz_id,
            "question": payload.question,
            "options": payload.options,
        }
        attempt = await self.atlas.insert_attempt(
            {
                "workspace_id": workspace_id,
                "user_id": user.id,
                "exam_type": "practice",
                "subject_kind": None,
                "subject_id": None,
                "subject_name": "Flashcards Questions",
                "status": "in_progress",
                "sequence_number": sequence,
                "question_count": 1,
                "correct_count": 0,
                "points_earned": 0,
                "quota_snapshot": {"exam_type": "practice"},
                "questions": [question],
            }
        )
        result = await self._grade_and_record(
            user=user,
            workspace_id=workspace_id,
            attempt=attempt,
            payload=AnswerSubmitRequest(
                quiz_id=payload.quiz_id,
                question=payload.question,
                options=payload.options,
                selected_index=payload.selected_index,
            ),
            allow_any_quiz=True,
        )
        await self.atlas.update_attempt(
            str(attempt["id"]),
            {
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
                "correct_count": 1 if result.correct else 0,
                "points_earned": result.points_total,
            },
        )
        return result

    async def access_status(self, *, workspace_id: str) -> AtlasAccessResponse:
        competition = await self.ensure_competition(workspace_id)
        return AtlasAccessResponse(
            student_access=bool(competition.get("student_access")),
            ends_at=competition["ends_at"],
            finalized=bool(competition.get("finalized_at")),
        )

    async def me(self, *, user: CurrentUser, workspace_id: str) -> AtlasMeResponse:
        await self.ensure_access(user, workspace_id)
        return await self._stats_for_user(workspace_id, user.id)

    async def leaderboard(self, *, user: CurrentUser, workspace_id: str) -> LeaderboardResponse:
        competition = await self.ensure_access(user, workspace_id)
        if competition.get("finalized_at") and competition.get("final_standings"):
            entries = [LeaderboardEntry.model_validate(row) for row in competition["final_standings"]]
            return LeaderboardResponse(
                platoon_total_ap=sum(entry.lifetime_ap for entry in entries),
                platoon_goal=competition.get("platoon_goal"),
                ends_at=competition["ends_at"],
                finalized=True,
                student_access=bool(competition.get("student_access")),
                entries=entries,
            )
        entries = await self._build_leaderboard(workspace_id)
        return LeaderboardResponse(
            platoon_total_ap=sum(entry.lifetime_ap for entry in entries),
            platoon_goal=competition.get("platoon_goal"),
            ends_at=competition["ends_at"],
            finalized=False,
            student_access=bool(competition.get("student_access")),
            entries=entries,
        )

    async def get_competition(self, *, user: CurrentUser, workspace_id: str) -> CompetitionSettingsResponse:
        if not is_admin(user):
            raise AtlasError("Only Academics can manage the competition.", status_code=403)
        row = await self.ensure_competition(workspace_id)
        return self._competition_response(row)

    async def update_competition(
        self,
        *,
        user: CurrentUser,
        workspace_id: str,
        payload: CompetitionSettingsUpdate,
    ) -> CompetitionSettingsResponse:
        if not is_admin(user):
            raise AtlasError("Only Academics can manage the competition.", status_code=403)
        await self.ensure_competition(workspace_id)
        changes: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if key in {"starts_at", "ends_at"} and value is not None:
                changes[key] = value.isoformat()
            else:
                changes[key] = value
        row = await self.atlas.update_competition(workspace_id, changes)
        return self._competition_response(row)

    async def finalize_competition(self, *, user: CurrentUser, workspace_id: str) -> CompetitionSettingsResponse:
        if not is_admin(user):
            raise AtlasError("Only Academics can finalize the competition.", status_code=403)
        await self.ensure_competition(workspace_id)
        entries = await self._build_leaderboard(workspace_id)
        row = await self.atlas.update_competition(
            workspace_id,
            {
                "finalized_at": datetime.now(UTC).isoformat(),
                "final_standings": [entry.model_dump(mode="json") for entry in entries],
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
        return self._competition_response(row)

    async def platoon_dashboard(self, *, user: CurrentUser, workspace_id: str) -> PlatoonDashboardResponse:
        if not is_admin(user):
            raise AtlasError("Platoon dashboard is limited to Academics.", status_code=403)
        competition = await self.ensure_competition(workspace_id)
        entries = await self._build_leaderboard(workspace_id)
        answers = await self.atlas.list_answers_for_workspace(workspace_id)
        attempts = await self.atlas.list_attempts_for_workspace(workspace_id)
        quizzes = {str(row["id"]): row for row in await self.list_all_quizzes(workspace_id)}
        sources = {
            str(row["id"]): source_label(row)
            for row in await self.sources.list_for_workspace(workspace_id, user.id)
        }
        lessons = {
            str(row["id"]): str(row.get("title") or "Class")
            for row in await self.lessons.list_with_children(workspace_id)
        }
        by_subject: dict[str, dict[str, Any]] = {}
        for answer in answers:
            quiz = quizzes.get(str(answer.get("quiz_id") or ""))
            if not quiz:
                continue
            if quiz.get("lesson_id"):
                kind = "lesson"
                subject_id = str(quiz["lesson_id"])
                name = lessons.get(subject_id, "Class")
            elif quiz.get("source_id"):
                kind = "source"
                subject_id = str(quiz["source_id"])
                name = sources.get(subject_id, "Source")
            else:
                continue
            key = f"{kind}:{subject_id}"
            bucket = by_subject.setdefault(
                key,
                {
                    "subject_kind": kind,
                    "subject_id": subject_id,
                    "subject_name": name,
                    "lifetime_ap": 0,
                    "correct": 0,
                    "total": 0,
                    "mastered_ids": set(),
                },
            )
            bucket["total"] += 1
            if answer.get("is_correct"):
                bucket["correct"] += 1
            bucket["lifetime_ap"] += int(answer.get("points_awarded") or 0)
        progress = await self.atlas.list_progress_for_workspace(workspace_id)
        for row in progress:
            if not row.get("mastered_at"):
                continue
            quiz = quizzes.get(str(row.get("quiz_id") or ""))
            if not quiz:
                continue
            if quiz.get("lesson_id"):
                key = f"lesson:{quiz['lesson_id']}"
            elif quiz.get("source_id"):
                key = f"source:{quiz['source_id']}"
            else:
                continue
            if key in by_subject:
                by_subject[key]["mastered_ids"].add(str(row["quiz_id"]))

        subject_rows = [
            SubjectBreakdown(
                subject_kind=bucket["subject_kind"],
                subject_id=bucket["subject_id"],
                subject_name=bucket["subject_name"],
                lifetime_ap=bucket["lifetime_ap"],
                concepts_mastered=len(bucket["mastered_ids"]),
                accuracy=accuracy_from_counts(bucket["correct"], bucket["total"]),
                questions_answered=bucket["total"],
            )
            for bucket in by_subject.values()
        ]
        subject_rows.sort(key=lambda row: (-row.lifetime_ap, row.subject_name.casefold()))
        total_correct = sum(1 for row in answers if row.get("is_correct"))
        return PlatoonDashboardResponse(
            platoon_total_ap=sum(entry.lifetime_ap for entry in entries),
            concepts_mastered=sum(entry.concepts_mastered for entry in entries),
            accuracy=accuracy_from_counts(total_correct, len(answers)),
            participants=sum(1 for entry in entries if entry.lifetime_ap > 0),
            completed_exams=sum(
                1
                for row in attempts
                if row.get("status") == "completed" and row.get("exam_type") in {"full_practice", "subject"}
            ),
            student_access=bool(competition.get("student_access")),
            ends_at=competition["ends_at"],
            finalized=bool(competition.get("finalized_at")),
            leaderboard=entries,
            by_subject=subject_rows,
        )

    async def _grade_and_record(
        self,
        *,
        user: CurrentUser,
        workspace_id: str,
        attempt: dict[str, Any],
        payload: AnswerSubmitRequest,
        allow_any_quiz: bool,
    ) -> AnswerSubmitResponse:
        existing = await self.atlas.get_answer(str(attempt["id"]), payload.quiz_id)
        if existing:
            progress = await self.atlas.get_progress(user.id, payload.quiz_id)
            lifetime = await self._lifetime_ap(workspace_id, user.id)
            return AnswerSubmitResponse(
                correct=bool(existing.get("is_correct")),
                right_answer="",
                explanation=None,
                points_awarded=[],
                points_total=int(existing.get("points_awarded") or 0),
                correct_count=int(progress["correct_count"]) if progress else 0,
                mastered=bool(progress and progress.get("mastered_at")),
                newly_mastered=False,
                lifetime_ap=lifetime,
                attempt_correct_count=int(attempt.get("correct_count") or 0),
                attempt_points_earned=int(attempt.get("points_earned") or 0),
            )

        questions = attempt.get("questions") or []
        planned = next((row for row in questions if str(row.get("quiz_id")) == payload.quiz_id), None)
        if not allow_any_quiz and planned is None:
            raise AtlasError("That question is not part of this exam.")
        if planned is not None:
            if list(planned.get("options") or []) != payload.options:
                raise AtlasError("Options no longer match this exam question.")
            if str(planned.get("question") or "") != payload.question:
                raise AtlasError("Question text no longer matches this exam question.")

        quiz = await self.assessments.get_quiz(payload.quiz_id, workspace_id)
        if not quiz:
            raise AtlasError("That question is not in this workspace.", status_code=404)
        try:
            correct, right = grade_shown_answer(
                quiz,
                question=payload.question,
                options=payload.options,
                selected_index=payload.selected_index,
            )
        except ShownAnswerError as exc:
            raise AtlasError(str(exc)) from exc

        progress = await self.atlas.get_progress(user.id, payload.quiz_id)
        events: list[tuple[str, int]] = []
        newly_mastered = False
        if correct:
            progress_payload, events, newly_mastered = apply_correct_progress(
                progress,
                workspace_id=workspace_id,
                user_id=user.id,
                quiz_id=payload.quiz_id,
            )
        else:
            progress_payload = apply_incorrect_progress(
                progress,
                workspace_id=workspace_id,
                user_id=user.id,
                quiz_id=payload.quiz_id,
            )
        progress = await self.atlas.upsert_progress(progress_payload)
        points_total = sum_points(events)
        question_index = next(
            (index for index, row in enumerate(questions) if str(row.get("quiz_id")) == payload.quiz_id),
            len(questions),
        )
        answer = await self.atlas.insert_answer(
            {
                "attempt_id": attempt["id"],
                "workspace_id": workspace_id,
                "user_id": user.id,
                "quiz_id": payload.quiz_id,
                "question_index": question_index,
                "question": payload.question,
                "options": payload.options,
                "selected_index": payload.selected_index,
                "is_correct": correct,
                "points_awarded": points_total,
            }
        )
        if events:
            await self.atlas.insert_score_events(
                [
                    {
                        "workspace_id": workspace_id,
                        "user_id": user.id,
                        "quiz_id": payload.quiz_id,
                        "attempt_id": attempt["id"],
                        "answer_id": answer["id"],
                        "event_type": event_type,
                        "points": points,
                    }
                    for event_type, points in events
                ]
            )
        answers = await self.atlas.list_answers_for_attempt(str(attempt["id"]))
        attempt_correct = sum(1 for row in answers if row.get("is_correct"))
        attempt_points = sum(int(row.get("points_awarded") or 0) for row in answers)
        await self.atlas.update_attempt(
            str(attempt["id"]),
            {"correct_count": attempt_correct, "points_earned": attempt_points},
        )
        lifetime = await self._lifetime_ap(workspace_id, user.id)
        return AnswerSubmitResponse(
            correct=correct,
            right_answer=right,
            explanation=str(quiz.get("explanation") or "") or None,
            points_awarded=[PointsAwarded(event_type=event_type, points=points) for event_type, points in events],
            points_total=points_total,
            correct_count=int(progress["correct_count"]),
            mastered=bool(progress.get("mastered_at")),
            newly_mastered=newly_mastered,
            lifetime_ap=lifetime,
            attempt_correct_count=attempt_correct,
            attempt_points_earned=attempt_points,
        )

    async def _lifetime_ap(self, workspace_id: str, user_id: str) -> int:
        events = await self.atlas.list_score_events_for_user(workspace_id, user_id)
        return sum(int(row.get("points") or 0) for row in events)

    async def _stats_for_user(self, workspace_id: str, user_id: str) -> AtlasMeResponse:
        events = await self.atlas.list_score_events_for_user(workspace_id, user_id)
        progress = await self.atlas.list_progress_for_user(workspace_id, user_id)
        answers = await self.atlas.list_answers_for_user(workspace_id, user_id)
        correct = sum(1 for row in answers if row.get("is_correct"))
        return AtlasMeResponse(
            lifetime_ap=sum(int(row.get("points") or 0) for row in events),
            concepts_mastered=sum(1 for row in progress if row.get("mastered_at")),
            accuracy=accuracy_from_counts(correct, len(answers)),
            questions_answered=len(answers),
            correct_answers=correct,
        )

    async def _build_leaderboard(self, workspace_id: str) -> list[LeaderboardEntry]:
        roster = await self.atlas.list_approved_roster()
        auth_users = await self._list_auth_users()
        email_to_user = {
            str(row.get("email") or "").casefold(): str(row.get("id") or "")
            for row in auth_users
            if row.get("email") and row.get("id")
        }
        events = await self.atlas.list_score_events_for_workspace(workspace_id)
        progress = await self.atlas.list_progress_for_workspace(workspace_id)
        answers = await self.atlas.list_answers_for_workspace(workspace_id)
        ap_by_user: dict[str, int] = {}
        for row in events:
            user_id = str(row["user_id"])
            ap_by_user[user_id] = ap_by_user.get(user_id, 0) + int(row.get("points") or 0)
        mastered_by_user: dict[str, int] = {}
        for row in progress:
            if not row.get("mastered_at"):
                continue
            user_id = str(row["user_id"])
            mastered_by_user[user_id] = mastered_by_user.get(user_id, 0) + 1
        correct_by_user: dict[str, int] = {}
        total_by_user: dict[str, int] = {}
        for row in answers:
            user_id = str(row["user_id"])
            total_by_user[user_id] = total_by_user.get(user_id, 0) + 1
            if row.get("is_correct"):
                correct_by_user[user_id] = correct_by_user.get(user_id, 0) + 1

        raw_rows: list[dict[str, Any]] = []
        for person in roster:
            email = str(person.get("email") or "").casefold()
            user_id = email_to_user.get(email)
            if not user_id:
                # Include roster names with zero scores even before first login mapping fails.
                user_id = f"email:{email}"
            raw_rows.append(
                {
                    "user_id": user_id,
                    "name": str(person.get("name") or person.get("email") or "Student"),
                    "rank_title": person.get("rank"),
                    "lifetime_ap": ap_by_user.get(user_id, 0) if not user_id.startswith("email:") else 0,
                    "concepts_mastered": mastered_by_user.get(user_id, 0) if not user_id.startswith("email:") else 0,
                    "accuracy": accuracy_from_counts(
                        correct_by_user.get(user_id, 0),
                        total_by_user.get(user_id, 0),
                    )
                    if not user_id.startswith("email:")
                    else None,
                }
            )
        ordered = sort_leaderboard_rows(raw_rows)
        return [
            LeaderboardEntry(
                rank=index,
                user_id=str(row["user_id"]),
                name=str(row["name"]),
                rank_title=row.get("rank_title"),
                lifetime_ap=int(row["lifetime_ap"]),
                concepts_mastered=int(row["concepts_mastered"]),
                accuracy=row.get("accuracy"),
            )
            for index, row in enumerate(ordered, start=1)
        ]

    async def _list_auth_users(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        page = 1
        per_page = 200
        while True:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get(
                        f"{self.settings.supabase_url}/auth/v1/admin/users",
                        headers={
                            "apikey": self.settings.supabase_service_role_key,
                            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
                        },
                        params={"page": page, "per_page": per_page},
                    )
            except httpx.HTTPError as exc:
                raise AtlasError("Could not load roster identities.", status_code=502) from exc
            if response.status_code >= 400:
                raise AtlasError("Could not load roster identities.", status_code=502)
            payload = response.json()
            batch = payload.get("users") if isinstance(payload, dict) else payload
            if not isinstance(batch, list):
                break
            users.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return users

    def _attempt_response(self, row: dict[str, Any], answers: list[dict[str, Any]]) -> ExamAttemptResponse:
        questions = [ExamQuestion.model_validate(item) for item in (row.get("questions") or [])]
        return ExamAttemptResponse(
            id=str(row["id"]),
            exam_type=row["exam_type"],
            subject_kind=row.get("subject_kind"),
            subject_id=str(row["subject_id"]) if row.get("subject_id") else None,
            subject_name=row.get("subject_name"),
            status=str(row["status"]),
            sequence_number=int(row["sequence_number"]),
            started_at=row["started_at"],
            completed_at=row.get("completed_at"),
            question_count=int(row["question_count"]),
            correct_count=int(row.get("correct_count") or 0),
            points_earned=int(row.get("points_earned") or 0),
            quota_snapshot=row.get("quota_snapshot") or {},
            questions=questions,
            answered_quiz_ids=[str(answer["quiz_id"]) for answer in answers],
        )

    def _competition_response(self, row: dict[str, Any]) -> CompetitionSettingsResponse:
        standings = None
        if row.get("final_standings"):
            standings = [LeaderboardEntry.model_validate(item) for item in row["final_standings"]]
        return CompetitionSettingsResponse(
            workspace_id=str(row["workspace_id"]),
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
            platoon_goal=row.get("platoon_goal"),
            student_access=bool(row.get("student_access")),
            finalized_at=row.get("finalized_at"),
            final_standings=standings,
            updated_at=row["updated_at"],
        )
