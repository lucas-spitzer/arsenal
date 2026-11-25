"""Atlas Points award rules and progress updates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

MASTERED_AFTER = 5
FIRST_CORRECT_POINTS = 5
REPEAT_CORRECT_POINTS = 1
MASTERY_BONUS_POINTS = 3


def points_for_correct_answer(prior_correct_count: int) -> list[tuple[str, int]]:
    """Return score events for one newly validated correct answer.

    ``prior_correct_count`` is the count *before* this answer.
    """
    next_count = prior_correct_count + 1
    if prior_correct_count <= 0:
        events: list[tuple[str, int]] = [("first_correct", FIRST_CORRECT_POINTS)]
    else:
        events = [("repeat_correct", REPEAT_CORRECT_POINTS)]
    if next_count == MASTERED_AFTER:
        events.append(("mastery_bonus", MASTERY_BONUS_POINTS))
    return events


def apply_correct_progress(row: dict[str, Any] | None, *, workspace_id: str, user_id: str, quiz_id: str) -> tuple[dict[str, Any], list[tuple[str, int]], bool]:
    """Build the next progress row and score events for a correct answer."""
    now = datetime.now(UTC).isoformat()
    prior = int(row["correct_count"]) if row else 0
    incorrect = int(row["incorrect_count"]) if row else 0
    events = points_for_correct_answer(prior)
    next_count = prior + 1
    newly_mastered = next_count == MASTERED_AFTER
    mastered_at = row.get("mastered_at") if row else None
    if newly_mastered:
        mastered_at = now
    payload = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "quiz_id": quiz_id,
        "correct_count": next_count,
        "incorrect_count": incorrect,
        "mastered_at": mastered_at,
        "last_correct_at": now,
        "updated_at": now,
    }
    return payload, events, newly_mastered


def apply_incorrect_progress(row: dict[str, Any] | None, *, workspace_id: str, user_id: str, quiz_id: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    prior_correct = int(row["correct_count"]) if row else 0
    prior_incorrect = int(row["incorrect_count"]) if row else 0
    return {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "quiz_id": quiz_id,
        "correct_count": prior_correct,
        "incorrect_count": prior_incorrect + 1,
        "mastered_at": row.get("mastered_at") if row else None,
        "last_correct_at": row.get("last_correct_at") if row else None,
        "updated_at": now,
    }


def sum_points(events: list[tuple[str, int]]) -> int:
    return sum(points for _, points in events)


def accuracy_from_counts(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((correct / total) * 100)


def sort_leaderboard_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tie-break: AP desc, mastered desc, accuracy desc, name asc."""

    def key(row: dict[str, Any]) -> tuple[int, int, float, str]:
        accuracy = row.get("accuracy")
        accuracy_sort = float(accuracy) if isinstance(accuracy, (int, float)) else -1.0
        name = str(row.get("name") or "").casefold()
        return (
            -int(row.get("lifetime_ap") or 0),
            -int(row.get("concepts_mastered") or 0),
            -accuracy_sort,
            name,
        )

    return sorted(rows, key=key)


def _happened_by(value: Any, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    if not value:
        return False
    when = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when <= cutoff


def leaderboard_stats(
    events: list[dict[str, Any]],
    progress: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    *,
    as_of: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-user AP, mastery, and accuracy, counting only activity at or before ``as_of``."""
    ap: dict[str, int] = {}
    mastered: dict[str, int] = {}
    correct: dict[str, int] = {}
    total: dict[str, int] = {}
    for row in events:
        if _happened_by(row.get("created_at"), as_of):
            user_id = str(row["user_id"])
            ap[user_id] = ap.get(user_id, 0) + int(row.get("points") or 0)
    for row in progress:
        if row.get("mastered_at") and _happened_by(row.get("mastered_at"), as_of):
            user_id = str(row["user_id"])
            mastered[user_id] = mastered.get(user_id, 0) + 1
    for row in answers:
        if _happened_by(row.get("submitted_at"), as_of):
            user_id = str(row["user_id"])
            total[user_id] = total.get(user_id, 0) + 1
            if row.get("is_correct"):
                correct[user_id] = correct.get(user_id, 0) + 1
    return {
        user_id: {
            "lifetime_ap": ap.get(user_id, 0),
            "concepts_mastered": mastered.get(user_id, 0),
            "accuracy": accuracy_from_counts(correct.get(user_id, 0), total.get(user_id, 0)),
        }
        for user_id in set(ap) | set(mastered) | set(total)
    }


def rank_movement(current: list[dict[str, Any]], prior: list[dict[str, Any]]) -> dict[str, int]:
    """Places gained per user (positive = moved up) between two unsorted standings."""
    prior_rank = {str(row["user_id"]): rank for rank, row in enumerate(sort_leaderboard_rows(prior), start=1)}
    return {
        str(row["user_id"]): prior_rank.get(str(row["user_id"]), rank) - rank
        for rank, row in enumerate(sort_leaderboard_rows(current), start=1)
    }
