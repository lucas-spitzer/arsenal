"""Per-student Atlas Points dashboard aggregation. Pure functions, no I/O."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.atlas_scoring import accuracy_from_counts

Subject = tuple[str, str]

PLATOON_DASHBOARD = "platoon"
WEAK_QUESTION_LIMIT = 10
ACTIVITY_DAYS = 30


def quiz_subject(quiz: dict[str, Any] | None) -> Subject | None:
    """A class question belongs to its lesson; otherwise to its book."""
    if not quiz:
        return None
    if quiz.get("lesson_id"):
        return ("lesson", str(quiz["lesson_id"]))
    if quiz.get("source_id"):
        return ("source", str(quiz["source_id"]))
    return None


def _in_scope(quiz: dict[str, Any] | None, scope: Subject | None) -> bool:
    subject = quiz_subject(quiz)
    if subject is None:
        return False
    return scope is None or subject == scope


def subject_options(
    answers: list[dict[str, Any]],
    quizzes: dict[str, dict[str, Any]],
    names: dict[Subject, str],
) -> list[dict[str, Any]]:
    """Subjects the student has answered at least once, by name."""
    seen: dict[Subject, str] = {}
    for answer in answers:
        subject = quiz_subject(quizzes.get(str(answer.get("quiz_id") or "")))
        if subject is None or subject in seen:
            continue
        seen[subject] = names.get(subject, "Class" if subject[0] == "lesson" else "Source")
    return sorted(
        (
            {"subject_kind": kind, "subject_id": subject_id, "subject_name": name}
            for (kind, subject_id), name in seen.items()
        ),
        key=lambda row: row["subject_name"].casefold(),
    )


def summary(
    *,
    answers: list[dict[str, Any]],
    progress: list[dict[str, Any]],
    events: list[dict[str, Any]],
    quizzes: dict[str, dict[str, Any]],
    scope: Subject | None,
    learners: int = 1,
) -> dict[str, Any]:
    """``learners`` scales the question total so platoon mastery reads as mastered of possible."""

    def scoped(row: dict[str, Any]) -> bool:
        return _in_scope(quizzes.get(str(row.get("quiz_id") or "")), scope)

    scoped_answers = [row for row in answers if scoped(row)]
    correct = sum(1 for row in scoped_answers if row.get("is_correct"))
    return {
        "lifetime_ap": sum(int(row.get("points") or 0) for row in events if scoped(row)),
        "concepts_mastered": sum(1 for row in progress if row.get("mastered_at") and scoped(row)),
        "total_questions": sum(1 for quiz in quizzes.values() if _in_scope(quiz, scope)) * max(1, learners),
        "accuracy": accuracy_from_counts(correct, len(scoped_answers)),
        "questions_answered": len(scoped_answers),
        "correct_answers": correct,
    }


def weak_questions(
    *,
    progress: list[dict[str, Any]],
    quizzes: dict[str, dict[str, Any]],
    names: dict[Subject, str],
    scope: Subject | None,
    limit: int = WEAK_QUESTION_LIMIT,
) -> list[dict[str, Any]]:
    """Missed at least once and not yet mastered. Most misses first, then fewest correct.

    Rows from several students on the same question add together.
    """
    by_quiz: dict[str, dict[str, Any]] = {}
    for row in progress:
        if row.get("mastered_at") or int(row.get("incorrect_count") or 0) <= 0:
            continue
        quiz_id = str(row.get("quiz_id") or "")
        quiz = quizzes.get(quiz_id)
        if not _in_scope(quiz, scope):
            continue
        assert quiz is not None
        subject = quiz_subject(quiz)
        assert subject is not None
        item = by_quiz.setdefault(
            quiz_id,
            {
                "quiz_id": quiz_id,
                "question": str(quiz.get("question") or ""),
                "subject_kind": subject[0],
                "subject_id": subject[1],
                "subject_name": names.get(subject, "Class" if subject[0] == "lesson" else "Source"),
                "correct_count": 0,
                "incorrect_count": 0,
            },
        )
        item["correct_count"] += int(row.get("correct_count") or 0)
        item["incorrect_count"] += int(row.get("incorrect_count") or 0)
    rows = list(by_quiz.values())
    rows.sort(key=lambda item: (-item["incorrect_count"], item["correct_count"], item["question"].casefold()))
    return rows[:limit]


def resolve_zone(tz: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _local_day(value: Any, zone: ZoneInfo) -> date | None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(zone).date()


def daily_activity(
    *,
    answers: list[dict[str, Any]],
    events: list[dict[str, Any]],
    quizzes: dict[str, dict[str, Any]],
    scope: Subject | None,
    tz: str | None,
    now: datetime | None = None,
    days: int = ACTIVITY_DAYS,
) -> list[dict[str, Any]]:
    """One row per local day, oldest first, ending today."""
    zone = resolve_zone(tz)
    today = (now or datetime.now(UTC)).astimezone(zone).date()
    first = today - timedelta(days=days - 1)
    buckets = {
        first + timedelta(days=offset): {"answered": 0, "correct": 0, "points": 0}
        for offset in range(days)
    }
    for row in answers:
        if not _in_scope(quizzes.get(str(row.get("quiz_id") or "")), scope):
            continue
        day = _local_day(row.get("submitted_at"), zone)
        if day in buckets:
            buckets[day]["answered"] += 1
            if row.get("is_correct"):
                buckets[day]["correct"] += 1
    for row in events:
        if not _in_scope(quizzes.get(str(row.get("quiz_id") or "")), scope):
            continue
        day = _local_day(row.get("created_at"), zone)
        if day in buckets:
            buckets[day]["points"] += int(row.get("points") or 0)
    return [{"day": day.isoformat(), **counts} for day, counts in sorted(buckets.items())]
