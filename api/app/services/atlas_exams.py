"""Full Practice and Subject exam question assembly."""

from __future__ import annotations

import random
from typing import Any

from app.knowledge.answer_pool import AnswerPoolError, draw, pool_or_none

FULL_PRACTICE_SIZE = 30
SUBJECT_EXAM_SIZE = 10
WARFIGHTING_QUOTA = 10
LAND_NAV_QUOTA = 10
OTHER_QUOTA = 10

WARFIGHTING_SOURCE = "MCDP 1 Warfighting"
LAND_NAV_LESSON = "Land Navigation"
AFO_SOURCE = "Armed Forces Officer"

EXCLUDED_OTHER_NAMES = frozenset(
    {
        WARFIGHTING_SOURCE.casefold(),
        LAND_NAV_LESSON.casefold(),
        AFO_SOURCE.casefold(),
        "warfighting",
        "warfighting.pdf",
    }
)


class ExamAssemblyError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def normalize_label(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def source_label(source: dict[str, Any]) -> str:
    meta = source.get("source_metadata")
    if isinstance(meta, dict):
        display = meta.get("display_name")
        if isinstance(display, str) and display.strip():
            return display.strip()
    filename = str(source.get("filename") or "").strip()
    if "." in filename:
        return filename.rsplit(".", 1)[0]
    return filename or "Untitled source"


def is_warfighting_source(source: dict[str, Any]) -> bool:
    label = normalize_label(source_label(source))
    return label == normalize_label(WARFIGHTING_SOURCE) or label.startswith("mcdp 1") or label == "warfighting"


def is_afo_source(source: dict[str, Any]) -> bool:
    label = normalize_label(source_label(source))
    return label == normalize_label(AFO_SOURCE) or label in {"afo", "armed forces officer"}


def is_land_nav_lesson(lesson: dict[str, Any]) -> bool:
    return normalize_label(str(lesson.get("title") or "")) == normalize_label(LAND_NAV_LESSON)


def subject_key(kind: str, subject_id: str) -> str:
    return f"{kind}:{subject_id}"


def eligible_quizzes(quizzes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """MC items with a usable stem and answer."""
    out: list[dict[str, Any]] = []
    for quiz in quizzes:
        question = str(quiz.get("question") or "").strip()
        if not question:
            continue
        options = quiz.get("options")
        pool = pool_or_none(quiz.get("answer_pool"))
        if pool is None and (not isinstance(options, list) or len(options) < 2):
            continue
        out.append(quiz)
    return out


def quizzes_for_source(quizzes: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    return [quiz for quiz in quizzes if str(quiz.get("source_id") or "") == source_id and not quiz.get("lesson_id")]


def quizzes_for_lesson(quizzes: list[dict[str, Any]], lesson_id: str) -> list[dict[str, Any]]:
    return [quiz for quiz in quizzes if str(quiz.get("lesson_id") or "") == lesson_id]


def draw_shown_question(quiz: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    pool = pool_or_none(quiz.get("answer_pool"))
    subtype = str(quiz.get("subtype") or quiz.get("question_type") or "multiple_choice")
    if pool is not None:
        try:
            drawn = draw(pool, subtype, rng=rng)
            return {
                "quiz_id": str(quiz["id"]),
                "question": drawn.question or str(quiz.get("question") or ""),
                "options": list(drawn.options),
            }
        except AnswerPoolError:
            pass
    options = [str(option) for option in (quiz.get("options") or [])]
    shuffled = list(options)
    rng.shuffle(shuffled)
    return {
        "quiz_id": str(quiz["id"]),
        "question": str(quiz.get("question") or ""),
        "options": shuffled,
    }


def _sample_unique(pool: list[dict[str, Any]], count: int, rng: random.Random, used: set[str]) -> list[dict[str, Any]]:
    available = [quiz for quiz in pool if str(quiz["id"]) not in used]
    if len(available) < count:
        raise ExamAssemblyError(
            f"Need {count} eligible questions but only {len(available)} remain in this pool.",
        )
    picked = rng.sample(available, count)
    for quiz in picked:
        used.add(str(quiz["id"]))
    return picked


def assemble_subject_exam(
    quizzes: list[dict[str, Any]],
    *,
    subject_kind: str,
    subject_id: str,
    subject_name: str,
    rng: random.Random | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = rng or random.Random()
    pool = eligible_quizzes(
        quizzes_for_source(quizzes, subject_id) if subject_kind == "source" else quizzes_for_lesson(quizzes, subject_id)
    )
    if len(pool) < SUBJECT_EXAM_SIZE:
        raise ExamAssemblyError(
            f"{subject_name} needs at least {SUBJECT_EXAM_SIZE} eligible questions (has {len(pool)}).",
        )
    used: set[str] = set()
    picked = _sample_unique(pool, SUBJECT_EXAM_SIZE, rng, used)
    rng.shuffle(picked)
    shown = []
    for quiz in picked:
        item = draw_shown_question(quiz, rng)
        item.update(
            {
                "subject_kind": subject_kind,
                "subject_id": subject_id,
                "subject_name": subject_name,
                "visual": quiz.get("visual") if isinstance(quiz.get("visual"), dict) else None,
            }
        )
        shown.append(item)
    snapshot = {
        "exam_type": "subject",
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "question_count": SUBJECT_EXAM_SIZE,
    }
    return shown, snapshot


def assemble_full_practice(
    quizzes: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    lessons: list[dict[str, Any]],
    *,
    rng: random.Random | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = rng or random.Random()
    all_eligible = eligible_quizzes(quizzes)
    by_id = {str(quiz["id"]): quiz for quiz in all_eligible}

    warfighting = next((source for source in sources if is_warfighting_source(source)), None)
    land_nav = next((lesson for lesson in lessons if is_land_nav_lesson(lesson)), None)
    if warfighting is None:
        raise ExamAssemblyError(f"Missing source {WARFIGHTING_SOURCE}.")
    if land_nav is None:
        raise ExamAssemblyError(f"Missing lesson {LAND_NAV_LESSON}.")

    warfighting_pool = eligible_quizzes(quizzes_for_source(all_eligible, str(warfighting["id"])))
    land_nav_pool = eligible_quizzes(quizzes_for_lesson(all_eligible, str(land_nav["id"])))
    if len(warfighting_pool) < WARFIGHTING_QUOTA:
        raise ExamAssemblyError(
            f"{WARFIGHTING_SOURCE} needs {WARFIGHTING_QUOTA} questions (has {len(warfighting_pool)}).",
        )
    if len(land_nav_pool) < LAND_NAV_QUOTA:
        raise ExamAssemblyError(
            f"{LAND_NAV_LESSON} needs {LAND_NAV_QUOTA} questions (has {len(land_nav_pool)}).",
        )

    other_subjects: dict[str, dict[str, Any]] = {}
    for source in sources:
        if is_warfighting_source(source) or is_afo_source(source):
            continue
        label = source_label(source)
        if normalize_label(label) in EXCLUDED_OTHER_NAMES:
            continue
        pool = eligible_quizzes(quizzes_for_source(all_eligible, str(source["id"])))
        if not pool:
            continue
        other_subjects[subject_key("source", str(source["id"]))] = {
            "kind": "source",
            "id": str(source["id"]),
            "name": label,
            "pool": pool,
        }
    for lesson in lessons:
        if is_land_nav_lesson(lesson):
            continue
        title = str(lesson.get("title") or "").strip() or "Untitled class"
        if normalize_label(title) in EXCLUDED_OTHER_NAMES:
            continue
        pool = eligible_quizzes(quizzes_for_lesson(all_eligible, str(lesson["id"])))
        if not pool:
            continue
        other_subjects[subject_key("lesson", str(lesson["id"]))] = {
            "kind": "lesson",
            "id": str(lesson["id"]),
            "name": title,
            "pool": pool,
        }

    if not other_subjects:
        raise ExamAssemblyError("No other sources or lessons have eligible questions for the open quota.")

    used: set[str] = set()
    picked: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []

    for quiz in _sample_unique(warfighting_pool, WARFIGHTING_QUOTA, rng, used):
        picked.append(quiz)
        meta.append({"kind": "source", "id": str(warfighting["id"]), "name": source_label(warfighting)})
    for quiz in _sample_unique(land_nav_pool, LAND_NAV_QUOTA, rng, used):
        picked.append(quiz)
        meta.append({"kind": "lesson", "id": str(land_nav["id"]), "name": str(land_nav.get("title") or LAND_NAV_LESSON)})

    # Guarantee each other subject contributes at least one candidate when possible,
    # then fill the remaining open slots from the combined remainder.
    guaranteed: list[dict[str, Any]] = []
    guaranteed_meta: list[dict[str, Any]] = []
    subject_items = list(other_subjects.values())
    rng.shuffle(subject_items)
    for subject in subject_items:
        if len(guaranteed) >= OTHER_QUOTA:
            break
        available = [quiz for quiz in subject["pool"] if str(quiz["id"]) not in used]
        if not available:
            continue
        quiz = rng.choice(available)
        used.add(str(quiz["id"]))
        guaranteed.append(quiz)
        guaranteed_meta.append({"kind": subject["kind"], "id": subject["id"], "name": subject["name"]})

    remaining_needed = OTHER_QUOTA - len(guaranteed)
    remainder_pool = [
        quiz
        for subject in other_subjects.values()
        for quiz in subject["pool"]
        if str(quiz["id"]) not in used
    ]
    if remaining_needed > 0:
        if len(remainder_pool) < remaining_needed:
            raise ExamAssemblyError(
                f"Open quota needs {OTHER_QUOTA} questions; only {len(guaranteed) + len(remainder_pool)} available "
                f"outside {WARFIGHTING_SOURCE}, {AFO_SOURCE}, and {LAND_NAV_LESSON}.",
            )
        extra = rng.sample(remainder_pool, remaining_needed)
        for quiz in extra:
            used.add(str(quiz["id"]))
            subject = next(
                item
                for item in other_subjects.values()
                if any(str(row["id"]) == str(quiz["id"]) for row in item["pool"])
            )
            guaranteed.append(quiz)
            guaranteed_meta.append({"kind": subject["kind"], "id": subject["id"], "name": subject["name"]})

    picked.extend(guaranteed)
    meta.extend(guaranteed_meta)

    if len(picked) != FULL_PRACTICE_SIZE:
        raise ExamAssemblyError(f"Full practice must contain {FULL_PRACTICE_SIZE} questions (built {len(picked)}).")

    order = list(range(FULL_PRACTICE_SIZE))
    rng.shuffle(order)
    shown: list[dict[str, Any]] = []
    for index in order:
        quiz = by_id[str(picked[index]["id"])]
        item = draw_shown_question(quiz, rng)
        subject = meta[index]
        item.update(
            {
                "subject_kind": subject["kind"],
                "subject_id": subject["id"],
                "subject_name": subject["name"],
                "visual": quiz.get("visual") if isinstance(quiz.get("visual"), dict) else None,
            }
        )
        shown.append(item)

    snapshot = {
        "exam_type": "full_practice",
        "quotas": {
            "warfighting": WARFIGHTING_QUOTA,
            "land_navigation": LAND_NAV_QUOTA,
            "other": OTHER_QUOTA,
        },
        "warfighting_source_id": str(warfighting["id"]),
        "land_nav_lesson_id": str(land_nav["id"]),
        "other_subjects": [
            {"kind": item["kind"], "id": item["id"], "name": item["name"]} for item in other_subjects.values()
        ],
        "question_count": FULL_PRACTICE_SIZE,
    }
    return shown, snapshot
