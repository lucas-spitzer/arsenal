"""Grade a short-answer quiz response against stored criteria."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.services.openai_client import OpenAIClient

SHORT_ANSWER_GRADER_PROMPT = (
    "You are grading a short written answer for a second lieutenant studying at "
    "The Basic School. You are an unofficial study check. Do not present yourself "
    "as the school, an instructor, or the Marine Corps.\n\n"
    "Judge the learner's response ONLY against the evaluation criteria and the "
    "optional explanation provided. Do not invent doctrine or add requirements "
    "that are not listed.\n\n"
    "Return JSON with keys: passed (bool), feedback (string), "
    "met_criteria (string[]), missed_criteria (string[]).\n"
    "Feedback must be plain, brief, and usable for study. Say what was covered "
    "and what was missing."
)


@dataclass(frozen=True)
class ShortAnswerGrade:
    passed: bool
    feedback: str
    met_criteria: list[str]
    missed_criteria: list[str]


def parse_short_answer_grade(content: dict[str, Any]) -> ShortAnswerGrade:
    return ShortAnswerGrade(
        passed=bool(content.get("passed", False)),
        feedback=str(content.get("feedback") or "").strip(),
        met_criteria=[str(item) for item in content.get("met_criteria") or []],
        missed_criteria=[str(item) for item in content.get("missed_criteria") or []],
    )


def grade_short_answer(
    *,
    question: str,
    criteria: list[str],
    explanation: str | None,
    learner_answer: str,
    client: OpenAIClient,
    model: str,
) -> ShortAnswerGrade:
    payload = {
        "question": question,
        "evaluation_criteria": criteria,
        "explanation": explanation or "",
        "learner_answer": learner_answer,
    }
    result = client.complete_json(
        system_prompt=SHORT_ANSWER_GRADER_PROMPT,
        user_prompt=json.dumps(payload),
        model=model,
    )
    return parse_short_answer_grade(result.content)
