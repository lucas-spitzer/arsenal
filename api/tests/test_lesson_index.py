from __future__ import annotations

from typing import Any

from app.worker.lesson_index import LessonIndexer


class FakeEmbedder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError("quota exceeded")
        return [[0.1, 0.2] for _ in texts]


class FakeDb:
    def __init__(self, *, resource: dict[str, Any] | None = None, fail_embed: bool = False) -> None:
        self.embedding_client = FakeEmbedder(fail=fail_embed)
        self.lesson = {"id": "lesson-1", "workspace_id": "ws-1", "title": "Role of the Chaplain"}
        self.objectives = [
            {"id": "o1", "position": 1, "text": "Identify suicide warning signs.", "code": "MCS-VALU-1010b", "is_async": False},
            {"id": "o2", "position": 2, "text": "Identify suicide prevention resources.", "code": "MCS-VALU-1010c", "is_async": False},
        ]
        self.resource = resource
        self.statuses: list[dict[str, Any]] = []
        self.events: list[str] = []
        self.inserted: list[dict[str, Any]] = []

    def get_lesson(self, lesson_id: str) -> dict[str, Any] | None:
        return self.lesson if lesson_id == "lesson-1" else None

    def list_lesson_objectives(self, lesson_id: str) -> list[dict[str, Any]]:
        return self.objectives

    def get_lesson_resource(self, resource_id: str) -> dict[str, Any] | None:
        return self.resource

    def update_lesson_resource(self, resource_id: str, payload: dict[str, Any]) -> None:
        self.statuses.append(payload)

    def delete_lesson_chunks_for_resource(self, resource_id: str) -> None:
        self.events.append(f"delete-resource:{resource_id}")

    def delete_lesson_objective_chunks(self, lesson_id: str) -> None:
        self.events.append(f"delete-objectives:{lesson_id}")

    def insert_lesson_chunks(self, rows: list[dict[str, Any]]) -> None:
        self.events.append(f"insert:{len(rows)}")
        self.inserted.extend(rows)


class FakeStorage:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls: list[tuple[str, str | None]] = []

    def download(self, path: str, *, bucket: str | None = None) -> bytes:
        self.calls.append((path, bucket))
        return self.content


def _resource(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "res-1",
        "lesson_id": "lesson-1",
        "workspace_id": "ws-1",
        "kind": "file",
        "label": "Chaplain brief.txt",
        "filename": "Chaplain brief.txt",
        "storage_path": "tbs/lesson-1/abc-Chaplain-brief.txt",
    }
    row.update(overrides)
    return row


def test_index_resource_replaces_chunks_and_marks_ready() -> None:
    db = FakeDb(resource=_resource())
    storage = FakeStorage(b"Warning signs include withdrawal and talk of being a burden.")

    result = LessonIndexer(db, storage, bucket="lesson-files").index_resource("res-1")  # type: ignore[arg-type]

    assert result == {"resource_id": "res-1", "status": "ready", "chunks": 1}
    assert storage.calls == [("tbs/lesson-1/abc-Chaplain-brief.txt", "lesson-files")]
    assert db.events == ["delete-resource:res-1", "insert:1"]
    assert db.statuses[0] == {"index_status": "indexing", "index_error": None}
    assert db.statuses[-1] == {"index_status": "ready", "index_error": None}
    chunk = db.inserted[0]
    assert chunk["kind"] == "file_text"
    assert chunk["resource_id"] == "res-1"
    assert chunk["text"].startswith("Role of the Chaplain · Chaplain brief.txt · part 1\n")
    assert chunk["embedding"] == "[0.1,0.2]"


def test_embedding_failure_marks_failed_and_keeps_old_chunks() -> None:
    db = FakeDb(resource=_resource(), fail_embed=True)

    result = LessonIndexer(db, FakeStorage(b"Some text"), bucket="lesson-files").index_resource("res-1")  # type: ignore[arg-type]

    assert result["status"] == "failed"
    assert db.statuses[-1]["index_status"] == "failed"
    assert "quota exceeded" in db.statuses[-1]["index_error"]
    assert db.events == []


def test_legacy_format_is_skipped_without_download() -> None:
    db = FakeDb(resource=_resource(filename="brief.ppt", label="brief.ppt"))
    storage = FakeStorage(b"")

    result = LessonIndexer(db, storage, bucket="lesson-files").index_resource("res-1")  # type: ignore[arg-type]

    assert result["status"] == "skipped"
    assert storage.calls == []
    assert "PPTX" in db.statuses[-1]["index_error"]


def test_empty_text_marks_failed() -> None:
    db = FakeDb(resource=_resource())

    result = LessonIndexer(db, FakeStorage(b"   \n  "), bucket="lesson-files").index_resource("res-1")  # type: ignore[arg-type]

    assert result["status"] == "failed"
    assert "No readable text" in db.statuses[-1]["index_error"]


def test_links_and_missing_resources_are_ignored() -> None:
    db = FakeDb(resource=_resource(kind="link"))
    assert LessonIndexer(db, FakeStorage(b""), bucket="b").index_resource("res-1")["status"] == "missing"  # type: ignore[arg-type]
    assert db.statuses == []


def test_index_objectives_rebuilds_elo_chunks() -> None:
    db = FakeDb()

    result = LessonIndexer(db, FakeStorage(b""), bucket="lesson-files").index_objectives("lesson-1")  # type: ignore[arg-type]

    assert result == {"lesson_id": "lesson-1", "status": "ready", "chunks": 2}
    assert db.events == ["delete-objectives:lesson-1", "insert:2"]
    first = db.inserted[0]
    assert first["kind"] == "objective"
    assert first["objective_id"] == "o1"
    assert first["locator"] == {"position": 1, "code": "MCS-VALU-1010b"}
    assert first["text"] == "Role of the Chaplain — ELO 1: Identify suicide warning signs. (MCS-VALU-1010b)"


def test_index_objectives_with_no_elos_clears_chunks() -> None:
    db = FakeDb()
    db.objectives = []

    LessonIndexer(db, FakeStorage(b""), bucket="lesson-files").index_objectives("lesson-1")  # type: ignore[arg-type]

    assert db.events == ["delete-objectives:lesson-1", "insert:0"]
    assert db.embedding_client.calls == []
