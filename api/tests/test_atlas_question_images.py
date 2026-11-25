import asyncio
from types import SimpleNamespace

from app.models.atlas import ExamAttemptResponse
from app.routers.atlas import _with_question_images


class Storage:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def create_signed_url(self, *, bucket: str, path: str, expires_in: int) -> str:
        self.paths.append(path)
        return f"https://files.example/{path}"


SETTINGS = SimpleNamespace(sources_bucket="sources", signed_url_expires_seconds=3600)


def _attempt(questions: list[dict]) -> ExamAttemptResponse:
    return ExamAttemptResponse(
        id="att-1",
        exam_type="subject",
        status="in_progress",
        sequence_number=1,
        started_at="2026-11-24T00:00:00Z",
        question_count=len(questions),
        correct_count=0,
        points_earned=0,
        questions=questions,
    )


def test_exam_question_images_get_signed_urls() -> None:
    attempt = _attempt(
        [
            {
                "quiz_id": "q-1",
                "question": "What unit size is represented in the graphic?",
                "options": ["Squad", "Fireteam"],
                "visual": {"storage_path": "ws/visuals/Fireteam.png", "placement": "stem", "kind": "diagram"},
            },
            {"quiz_id": "q-2", "question": "No picture?", "options": ["A", "B"], "visual": None},
        ]
    )
    storage = Storage()
    signed = asyncio.run(_with_question_images(attempt, storage, SETTINGS))  # type: ignore[arg-type]

    assert storage.paths == ["ws/visuals/Fireteam.png"]
    visual = signed.questions[0].visual
    assert visual is not None
    assert visual["url"] == "https://files.example/ws/visuals/Fireteam.png"
    assert visual["placement"] == "stem"
    assert "storage_path" not in visual
    assert signed.questions[1].visual is None


def test_exam_without_images_skips_signing() -> None:
    attempt = _attempt([{"quiz_id": "q-1", "question": "Q?", "options": ["A", "B"]}])
    storage = Storage()
    assert asyncio.run(_with_question_images(attempt, storage, SETTINGS)) is attempt  # type: ignore[arg-type]
    assert storage.paths == []
