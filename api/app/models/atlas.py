from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ExamType = Literal["full_practice", "subject", "practice"]
SubjectKind = Literal["source", "lesson"]
ScoreEventType = Literal["first_correct", "repeat_correct", "mastery_bonus"]


class ExamStartRequest(BaseModel):
    exam_type: Literal["full_practice", "subject"]
    subject_kind: SubjectKind | None = None
    subject_id: str | None = None


class ExamQuestion(BaseModel):
    quiz_id: str
    question: str
    options: list[str]
    subtype: str | None = None
    subject_kind: SubjectKind | None = None
    subject_id: str | None = None
    subject_name: str | None = None
    visual: dict[str, Any] | None = None


class ExamAttemptResponse(BaseModel):
    id: str
    exam_type: ExamType
    subject_kind: SubjectKind | None = None
    subject_id: str | None = None
    subject_name: str | None = None
    status: str
    sequence_number: int
    started_at: datetime
    completed_at: datetime | None = None
    question_count: int
    correct_count: int
    points_earned: int
    quota_snapshot: dict[str, Any] = Field(default_factory=dict)
    questions: list[ExamQuestion] = Field(default_factory=list)
    answered_quiz_ids: list[str] = Field(default_factory=list)


class AnswerSubmitRequest(BaseModel):
    quiz_id: str
    question: str
    options: list[str] = Field(min_length=1)
    selected_index: int | None = Field(default=None, ge=0)
    selected_indices: list[int] | None = None


class PointsAwarded(BaseModel):
    event_type: ScoreEventType
    points: int


class AnswerSubmitResponse(BaseModel):
    correct: bool
    right_answer: str
    correct_options: list[str] = Field(default_factory=list)
    explanation: str | None = None
    feedback: str | None = None
    points_awarded: list[PointsAwarded] = Field(default_factory=list)
    points_total: int = 0
    correct_count: int
    mastered: bool
    newly_mastered: bool
    lifetime_ap: int
    attempt_correct_count: int
    attempt_points_earned: int


class PracticeAnswerRequest(BaseModel):
    quiz_id: str
    question: str
    options: list[str] = Field(default_factory=list)
    selected_index: int | None = Field(default=None, ge=0)
    selected_indices: list[int] | None = None
    response: str | None = None


class AtlasMeResponse(BaseModel):
    lifetime_ap: int
    concepts_mastered: int
    accuracy: float | None
    questions_answered: int
    correct_answers: int


class AtlasAccessResponse(BaseModel):
    student_access: bool
    ends_at: datetime
    finalized: bool


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    name: str
    rank_title: str | None = None
    lifetime_ap: int
    concepts_mastered: int
    accuracy: float | None
    movement_24h: int = 0


class LeaderboardResponse(BaseModel):
    platoon_total_ap: int
    platoon_goal: int | None = None
    ends_at: datetime
    finalized: bool
    student_access: bool
    entries: list[LeaderboardEntry]


class CompetitionSettingsResponse(BaseModel):
    workspace_id: str
    starts_at: datetime
    ends_at: datetime
    platoon_goal: int | None = None
    student_access: bool
    finalized_at: datetime | None = None
    final_standings: list[LeaderboardEntry] | None = None
    updated_at: datetime


class CompetitionSettingsUpdate(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    platoon_goal: int | None = None
    student_access: bool | None = None


class SubjectBreakdown(BaseModel):
    subject_kind: SubjectKind
    subject_id: str
    subject_name: str
    lifetime_ap: int
    concepts_mastered: int
    accuracy: float | None
    questions_answered: int


class DashboardSubject(BaseModel):
    subject_kind: SubjectKind
    subject_id: str
    subject_name: str


class DashboardSummary(BaseModel):
    lifetime_ap: int
    concepts_mastered: int
    total_questions: int
    accuracy: float | None
    questions_answered: int
    correct_answers: int


class DashboardWeakQuestion(BaseModel):
    quiz_id: str
    question: str
    subject_kind: SubjectKind
    subject_id: str
    subject_name: str
    correct_count: int
    incorrect_count: int


class DashboardDay(BaseModel):
    day: str
    answered: int
    correct: int
    points: int


class DashboardResponse(BaseModel):
    user_id: str
    subjects: list[DashboardSubject]
    summary: DashboardSummary
    weak_questions: list[DashboardWeakQuestion]
    activity: list[DashboardDay]
    active_days: int
    ends_at: datetime


class PlatoonDashboardResponse(BaseModel):
    platoon_total_ap: int
    concepts_mastered: int
    accuracy: float | None
    participants: int
    completed_exams: int
    student_access: bool
    ends_at: datetime
    finalized: bool
    leaderboard: list[LeaderboardEntry]
    by_subject: list[SubjectBreakdown]
