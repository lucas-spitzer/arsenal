import asyncio
import json
from typing import Any

import pytest

from app.services.library_artifacts import LibraryArtifactError, looks_like_mp3, upload_library_artifact

MP3 = b"ID3" + b"\x00" * 16


class _Storage:
    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    async def upload(
        self,
        *,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        upsert: bool = False,
        timeout: float = 120,
    ) -> dict[str, Any]:
        self.uploads.append(
            {
                "bucket": bucket,
                "path": path,
                "content": content,
                "content_type": content_type,
                "upsert": upsert,
                "timeout": timeout,
            },
        )
        return {}

    async def delete(self, *, bucket: str, path: str) -> None:
        self.deleted.append(path)


class _Artifacts:
    def __init__(self, existing: list[dict[str, Any]] | None = None) -> None:
        self.rows = list(existing or [])
        self.created: list[dict[str, Any]] = []

    async def list_for_source(
        self,
        source_id: str,
        workspace_id: str,
        *,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in self.rows
            if row.get("source_id") == source_id
            and row.get("workspace_id") == workspace_id
            and (artifact_type is None or row.get("artifact_type") == artifact_type)
        ]

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(payload)
        return payload


class _Wiki:
    def __init__(self, existing: list[dict[str, Any]] | None = None) -> None:
        self.existing = list(existing or [])
        self.inserted: list[dict[str, Any]] = []

    async def list_for_workspace(self, workspace_id: str, **_: Any) -> list[dict[str, Any]]:
        assert workspace_id == "ws-1"
        return list(self.existing)

    async def insert_many(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        saved = [{**row, "id": f"wiki-{len(self.inserted) + index}"} for index, row in enumerate(rows, start=1)]
        self.inserted.extend(saved)
        return saved

    async def update(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": entry_id, **payload}


class _Quizzes:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def insert_quizzes(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        saved = [{**row, "id": f"quiz-{len(self.rows) + index}"} for index, row in enumerate(rows, start=1)]
        self.rows.extend(saved)
        return saved


def _upload(
    *,
    artifact_type: str,
    filename: str,
    content: bytes,
    title: str = "Warfighting",
    artifacts: _Artifacts | None = None,
    wiki: _Wiki | None = None,
    quizzes: _Quizzes | None = None,
    storage: _Storage | None = None,
) -> tuple[dict[str, Any], _Artifacts, _Wiki, _Quizzes, _Storage]:
    artifact_rows = artifacts or _Artifacts()
    wiki_rows = wiki or _Wiki()
    quiz_rows = quizzes or _Quizzes()
    stored = storage or _Storage()
    result = asyncio.run(
        upload_library_artifact(
            workspace_id="ws-1",
            workspace_slug="acme",
            source={"id": "book-1", "slug": "warfighting"},
            artifact_type=artifact_type,
            title=title,
            filename=filename,
            content=content,
            json_max_bytes=1024 * 1024,
            bucket="sources",
            artifacts=artifact_rows,  # type: ignore[arg-type]
            wiki_entries=wiki_rows,  # type: ignore[arg-type]
            assessments=quiz_rows,  # type: ignore[arg-type]
            storage=stored,  # type: ignore[arg-type]
        ),
    )
    return result, artifact_rows, wiki_rows, quiz_rows, stored


def test_looks_like_mp3_accepts_id3_and_frame_sync() -> None:
    assert looks_like_mp3(MP3)
    assert looks_like_mp3(bytes([0xFF, 0xFB, 0x90, 0x00]))
    assert not looks_like_mp3(b'{"terms": []}')


def test_audiobook_upload_stores_a_playable_mp3_on_the_source() -> None:
    result, artifacts, wiki, quizzes, storage = _upload(
        artifact_type="audiobook",
        filename="Warfighting.mp3",
        content=MP3,
        title="Warfighting",
    )

    assert result["artifact_type"] == "audiobook"
    assert result["question_count"] == 0
    assert wiki.inserted == []
    assert quizzes.rows == []
    created = artifacts.created[0]
    assert created["artifact_type"] == "audiobook"
    assert created["source_id"] == "book-1"
    assert created["production_run_id"] is None
    assert created["format"] == "mp3"
    assert created["filename"] == "Warfighting.mp3"
    assert created["storage_path"] == "acme/warfighting/audiobooks/warfighting.mp3"
    assert created["manifest"] == {"title": "Warfighting", "status": "ready"}
    assert created["origin"] == {"source": "library_upload"}
    assert storage.uploads[0]["content_type"] == "audio/mpeg"
    assert storage.uploads[0]["content"] == MP3
    assert storage.deleted == []


def test_second_audiobook_with_the_same_title_gets_a_new_path() -> None:
    existing = _Artifacts(
        [
            {
                "source_id": "book-1",
                "workspace_id": "ws-1",
                "artifact_type": "audiobook",
                "storage_path": "acme/warfighting/audiobooks/warfighting.mp3",
            },
        ],
    )
    _result, artifacts, _wiki, _quizzes, storage = _upload(
        artifact_type="audiobook",
        filename="again.mp3",
        content=MP3,
        artifacts=existing,
    )
    assert artifacts.created[0]["storage_path"] == "acme/warfighting/audiobooks/warfighting-2.mp3"
    assert storage.uploads[0]["path"].endswith("/warfighting-2.mp3")


def test_audiobook_upload_rejects_a_file_that_is_not_mp3() -> None:
    with pytest.raises(LibraryArtifactError, match="not an MP3"):
        _upload(artifact_type="audiobook", filename="notes.mp3", content=b"not audio")
    with pytest.raises(LibraryArtifactError, match=".mp3"):
        _upload(artifact_type="audiobook", filename="notes.json", content=MP3)


def test_knowledge_json_writes_terms_lists_abbreviations_and_questions_without_a_project() -> None:
    content = json.dumps(
        {
            "terms": [
                {"term": "Friction", "definition": "The force that makes the simple difficult."},
            ],
            "key_lists": [
                {
                    "concept": "Centers of Gravity",
                    "overview": "Sources of strength.",
                    "items": ["People", "Installations"],
                },
            ],
            "abbreviations": [
                {
                    "abbreviation": "MEF",
                    "title": "Marine Expeditionary Force",
                    "definition": "The largest MAGTF.",
                    "category": "MAGTF",
                },
            ],
            "questions": [
                {
                    "question": "What does MEF stand for?",
                    "abbreviation": "MEF",
                    "correct": ["Marine Expeditionary Force"],
                    "distractors": [{"text": "Marine Expeditionary Brigade"}],
                },
                {
                    "question": "What resists action in war?",
                    "term": "Friction",
                    "correct": ["Friction"],
                    "distractors": [{"text": "Tempo"}],
                },
                {
                    "question": "Which idea names sources of strength?",
                    "concept": "Centers of Gravity",
                    "correct": ["Centers of Gravity"],
                    "distractors": [{"text": "Friction"}],
                },
            ],
        },
    ).encode()

    result, artifacts, wiki, quizzes, storage = _upload(
        artifact_type="knowledge",
        filename="notes.json",
        content=content,
        title="Chapter notes",
    )

    assert result["artifact"] is None
    assert result["wiki_entry_count"] == 3
    assert result["question_count"] == 3
    assert artifacts.created == []
    assert storage.uploads == []
    by_kind = {row["entry_kind"]: row for row in wiki.inserted}
    assert by_kind["term"]["preferred_label"] == "Friction"
    assert by_kind["list"]["preferred_label"] == "Centers of Gravity"
    assert by_kind["list"]["items"][0]["name"] == "People"
    abbreviation = by_kind["abbreviation"]
    assert abbreviation["preferred_label"] == "MEF"
    assert abbreviation["significance"] == "Marine Expeditionary Force"
    assert abbreviation["aliases"] == ["Marine Expeditionary Force"]
    assert "knowledge_project_id" not in abbreviation["origin"]
    assert abbreviation["origin"]["section_title"] == "Chapter notes"
    assert abbreviation["evidence"] == [{"source_id": "book-1"}]
    by_question = {row["question"]: row for row in quizzes.rows}
    assert "knowledge_project_id" not in by_question["What does MEF stand for?"]
    assert by_question["What does MEF stand for?"]["source_id"] == "book-1"
    assert by_question["What does MEF stand for?"]["citations"] == [
        {"uri": f"wiki://{abbreviation['id']}", "type": "wiki"},
    ]
    assert by_question["What resists action in war?"]["citations"] == [
        {"uri": f"wiki://{by_kind['term']['id']}", "type": "wiki"},
    ]
    assert by_question["Which idea names sources of strength?"]["citations"] == [
        {"uri": f"wiki://{by_kind['list']['id']}", "type": "wiki"},
    ]


def test_questions_only_json_lands_in_the_library_without_wiki_rows() -> None:
    content = json.dumps(
        {
            "questions": [
                {
                    "question": "Which force is the largest MAGTF?",
                    "correct": ["MEF"],
                    "distractors": [{"text": "MEB"}],
                },
            ],
        },
    ).encode()

    result, _artifacts, wiki, quizzes, _storage = _upload(
        artifact_type="knowledge",
        filename="questions.json",
        content=content,
        title="Questions",
    )

    assert result["wiki_entry_count"] == 0
    assert result["question_count"] == 1
    assert wiki.inserted == []
    assert quizzes.rows[0]["citations"] == []
    assert quizzes.rows[0]["origin"]["source"] == "structured_notes"
    assert "knowledge_project_id" not in quizzes.rows[0]


def test_question_can_cite_an_existing_term() -> None:
    wiki = _Wiki(
        [
            {
                "id": "wiki-friction",
                "preferred_label": "Friction",
                "entry_kind": "term",
                "definition": "Resistance.",
            },
        ],
    )
    content = json.dumps(
        {
            "questions": [
                {
                    "question": "What resists action in war?",
                    "term": "Friction",
                    "correct": ["Friction"],
                    "distractors": [{"text": "Tempo"}],
                },
            ],
        },
    ).encode()

    quizzes = _Quizzes()
    _result, _artifacts, _wiki, quizzes, _storage = _upload(
        artifact_type="knowledge",
        filename="questions.json",
        content=content,
        wiki=wiki,
        quizzes=quizzes,
    )
    assert quizzes.rows[0]["citations"] == [{"uri": "wiki://wiki-friction", "type": "wiki"}]


def test_unknown_question_citation_is_rejected() -> None:
    content = json.dumps(
        {
            "questions": [
                {
                    "question": "What does MEF stand for?",
                    "abbreviation": "MEF",
                    "correct": ["Marine Expeditionary Force"],
                    "distractors": [{"text": "Marine Expeditionary Brigade"}],
                },
            ],
        },
    ).encode()

    with pytest.raises(LibraryArtifactError, match="not in this file or the wiki"):
        _upload(artifact_type="knowledge", filename="questions.json", content=content)
