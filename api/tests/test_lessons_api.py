from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.dependencies.auth import require_admin
from app.models.auth import CurrentUser
from app.models.lesson import LessonCreate, LessonLinkCreate, LessonObjectivesReplace
from app.models.workspace import WorkspaceResponse
from app.repositories.lessons import LessonRepository, group_lessons
from app.routers import lessons as lessons_router
from app.routers.lessons import (
    add_lesson_link,
    create_lesson,
    delete_lesson,
    delete_lesson_resource,
    download_lesson_resource,
    list_lessons,
    reindex_all_lessons,
    replace_lesson_objectives,
    upload_lesson_files,
)
from app.services.lesson_files import LessonFileValidationError, skip_reason, validate_lesson_file
from app.services.supabase_rest import SupabaseRestError

PPTX_BYTES = b"PK\x03\x04" + b"\x00" * 32
PDF_BYTES = b"%PDF-1.7\n" + b"\x00" * 32


def _workspace() -> WorkspaceResponse:
    now = datetime.now(UTC)
    return WorkspaceResponse(
        id="ws-1",
        owner_id="owner-1",
        name="The Basic School",
        slug="the-basic-school",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def _user() -> CurrentUser:
    return CurrentUser(id="user-1", email="admin@example.com", role="admin")


def _settings() -> Any:
    return SimpleNamespace(
        lessons_bucket="lesson-files",
        max_lesson_file_bytes=1024 * 1024,
        signed_url_expires_seconds=600,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lesson(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "lesson-1",
        "workspace_id": "ws-1",
        "title": "Decision Making",
        "sort_order": 2,
        "notes": None,
        "created_by": "user-1",
        "created_at": _now(),
        "updated_at": _now(),
    }
    row.update(overrides)
    return row


def _resource(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "res-1",
        "lesson_id": "lesson-1",
        "workspace_id": "ws-1",
        "kind": "file",
        "label": "OODA.pptx",
        "position": 0,
        "url": None,
        "storage_path": "the-basic-school/lesson-1/abc-OODA.pptx",
        "filename": "OODA.pptx",
        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "file_size_bytes": 36,
        "index_status": "ready",
        "index_error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    row.update(overrides)
    return row


class FakeLessonRepo:
    def __init__(
        self,
        lessons: list[dict[str, Any]] | None = None,
        objectives: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        fail_resource_insert: bool = False,
        duplicate_title: bool = False,
    ) -> None:
        self.lessons = lessons or []
        self.objectives = objectives or []
        self.resources = resources or []
        self.fail_resource_insert = fail_resource_insert
        self.duplicate_title = duplicate_title
        self.deleted_lessons: list[str] = []
        self.deleted_resources: list[str] = []
        self.resource_updates: list[tuple[str, dict[str, Any]]] = []

    async def list_with_children(self, workspace_id: str) -> list[dict[str, Any]]:
        return group_lessons(
            [row for row in self.lessons if row["workspace_id"] == workspace_id],
            self.objectives,
            self.resources,
        )

    async def get_with_children(self, lesson_id: str, workspace_id: str) -> dict[str, Any] | None:
        lesson = await self.get(lesson_id, workspace_id)
        return group_lessons([lesson], self.objectives, self.resources)[0] if lesson else None

    async def get(self, lesson_id: str, workspace_id: str) -> dict[str, Any] | None:
        return next(
            (r for r in self.lessons if r["id"] == lesson_id and r["workspace_id"] == workspace_id),
            None,
        )

    async def next_sort_order(self, workspace_id: str) -> int:
        return len(self.lessons) + 1

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.duplicate_title:
            raise SupabaseRestError('duplicate key value violates unique constraint "lessons_workspace_title_key"')
        row = _lesson(id=f"lesson-{len(self.lessons) + 1}", **payload)
        self.lessons.append(row)
        return row

    async def delete(self, lesson_id: str, workspace_id: str) -> None:
        self.deleted_lessons.append(lesson_id)

    async def replace_objectives(
        self, lesson_id: str, workspace_id: str, objectives: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        self.objectives = [o for o in self.objectives if o["lesson_id"] != lesson_id]
        rows = [
            {"id": f"obj-{index}", "lesson_id": lesson_id, "workspace_id": workspace_id, "position": index, **item}
            for index, item in enumerate(objectives, start=1)
        ]
        self.objectives.extend(rows)
        return rows

    async def list_resources(self, lesson_id: str) -> list[dict[str, Any]]:
        return [r for r in self.resources if r["lesson_id"] == lesson_id]

    async def list_file_resources(self, workspace_id: str) -> list[dict[str, Any]]:
        return [r for r in self.resources if r["workspace_id"] == workspace_id and r["kind"] == "file"]

    async def get_resource(
        self, resource_id: str, lesson_id: str, workspace_id: str
    ) -> dict[str, Any] | None:
        return next(
            (
                r
                for r in self.resources
                if r["id"] == resource_id and r["lesson_id"] == lesson_id and r["workspace_id"] == workspace_id
            ),
            None,
        )

    async def next_resource_position(self, lesson_id: str) -> int:
        return len(await self.list_resources(lesson_id))

    async def create_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail_resource_insert:
            raise SupabaseRestError("insert failed")
        row = _resource(id=f"res-{len(self.resources) + 1}", **payload)
        self.resources.append(row)
        return row

    async def update_resource(
        self, resource_id: str, workspace_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        self.resource_updates.append((resource_id, payload))
        for row in self.resources:
            if row["id"] == resource_id:
                row.update(payload)
                return row
        return None

    async def delete_resource(self, resource_id: str, workspace_id: str) -> None:
        self.deleted_resources.append(resource_id)


class FakeStorage:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.deleted_paths: list[list[str]] = []
        self.signed: list[dict[str, Any]] = []

    async def upload(self, **kwargs: Any) -> dict[str, Any]:
        self.uploaded.append(kwargs)
        return {}

    async def delete(self, *, bucket: str, path: str) -> None:
        self.deleted.append(path)

    async def delete_paths(self, *, bucket: str, paths: list[str]) -> None:
        assert bucket == "lesson-files"
        self.deleted_paths.append(paths)

    async def create_signed_url(self, **kwargs: Any) -> str:
        self.signed.append(kwargs)
        return "https://signed.example/file"


class FakeQueue:
    def __init__(self) -> None:
        self.resources: list[str] = []
        self.objective_lessons: list[str] = []

    def resource(self, resource_id: str) -> bool:
        self.resources.append(resource_id)
        return True

    def objectives(self, lesson_id: str) -> bool:
        self.objective_lessons.append(lesson_id)
        return True


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=name)


def test_list_nests_objectives_and_resources() -> None:
    repo = FakeLessonRepo(
        lessons=[_lesson()],
        objectives=[
            {"id": "obj-1", "lesson_id": "lesson-1", "position": 1, "text": "Identify OODA.", "code": "MCS-CMBH-1002a", "is_async": True}
        ],
        resources=[_resource(), _resource(id="res-2", kind="link", label="MarineNet", url="https://elearning.mcele.usmc.mil/x", storage_path=None, filename=None)],
    )

    result = asyncio.run(list_lessons(_workspace(), repo))  # type: ignore[arg-type]

    assert [lesson.title for lesson in result] == ["Decision Making"]
    assert result[0].objectives[0].code == "MCS-CMBH-1002a"
    assert result[0].objectives[0].is_async is True
    assert [r.kind for r in result[0].resources] == ["file", "link"]
    assert "storage_path" not in result[0].resources[0].model_dump()


def test_write_routes_require_admin() -> None:
    open_routes = {("GET", "/workspaces/{workspace_id}/lessons"), ("GET", "/workspaces/{workspace_id}/lessons/{lesson_id}/resources/{resource_id}/download")}
    for route in lessons_router.router.routes:
        assert isinstance(route, APIRoute)
        for method in route.methods:
            calls = [dep.call for dep in route.dependant.dependencies]
            if (method, route.path) in open_routes:
                assert require_admin not in calls
            else:
                assert require_admin in calls, f"{method} {route.path} must require admin"


def test_create_lesson_saves_objectives_and_queues_index() -> None:
    repo = FakeLessonRepo()
    queue = FakeQueue()
    payload = LessonCreate(
        title="  Cardinal Virtues ",
        objectives=[{"text": "Define the four cardinal virtues.", "code": " MCS-VALU-1002m "}],  # type: ignore[list-item]
    )

    result = asyncio.run(create_lesson(payload, _workspace(), _user(), repo, queue))  # type: ignore[arg-type]

    assert result.title == "Cardinal Virtues"
    assert result.sort_order == 1
    assert [o.code for o in result.objectives] == ["MCS-VALU-1002m"]
    assert queue.objective_lessons == [result.id]


def test_create_lesson_duplicate_title_409() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            create_lesson(LessonCreate(title="Decision Making"), _workspace(), _user(), FakeLessonRepo(duplicate_title=True), FakeQueue())  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409


def test_replace_objectives_renumbers_and_requeues() -> None:
    repo = FakeLessonRepo(lessons=[_lesson()])
    queue = FakeQueue()
    payload = LessonObjectivesReplace(objectives=[{"text": "A"}, {"text": "B", "is_async": True}])  # type: ignore[list-item]

    result = asyncio.run(replace_lesson_objectives("lesson-1", payload, _workspace(), repo, queue))  # type: ignore[arg-type]

    assert [(o.position, o.text, o.is_async) for o in result.objectives] == [(1, "A", False), (2, "B", True)]
    assert queue.objective_lessons == ["lesson-1"]


def test_link_must_be_https() -> None:
    with pytest.raises(ValidationError):
        LessonLinkCreate(url="http://elearning.mcele.usmc.mil/moodle")
    with pytest.raises(ValidationError):
        LessonLinkCreate(url="javascript:alert(1)")
    link = LessonLinkCreate(label="  ", url=" https://elearning.mcele.usmc.mil/moodle/mod/h5pactivity/view.php?id=672795#h5pbookid=40930 ")
    assert link.label == "MarineNet"
    assert link.url.startswith("https://elearning.mcele.usmc.mil/")


def test_add_link_is_not_indexed() -> None:
    repo = FakeLessonRepo(lessons=[_lesson()])

    result = asyncio.run(
        add_lesson_link("lesson-1", LessonLinkCreate(url="https://elearning.mcele.usmc.mil/x"), _workspace(), _user(), repo)  # type: ignore[arg-type]
    )

    assert result.kind == "link"
    assert result.index_status == "skipped"


def test_validate_rejects_disallowed_and_mismatched_files() -> None:
    with pytest.raises(LessonFileValidationError):
        validate_lesson_file(filename="payload.exe", content=b"MZ\x00", max_bytes=1024)
    with pytest.raises(LessonFileValidationError):
        validate_lesson_file(filename="slides.pptx", content=b"not a zip", max_bytes=1024)
    with pytest.raises(LessonFileValidationError):
        validate_lesson_file(filename="big.pdf", content=PDF_BYTES * 100, max_bytes=64)
    name, mime = validate_lesson_file(filename="OODA Loop.pptx", content=PPTX_BYTES, max_bytes=1024)
    assert name == "OODA Loop.pptx"
    assert mime.endswith("presentationml.presentation")


def test_skip_reason_marks_unsearchable_types() -> None:
    assert skip_reason("slides.pptx") is None
    assert skip_reason("notes.docx") is None
    assert skip_reason("outline.pdf") is None
    assert "PPTX" in (skip_reason("old.ppt") or "")
    assert skip_reason("roster.xlsx")
    assert skip_reason("photo.jpg")


def test_upload_rejects_disallowed_type_before_storing() -> None:
    storage = FakeStorage()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            upload_lesson_files(
                "lesson-1",
                _workspace(),
                _user(),
                _settings(),
                FakeLessonRepo(lessons=[_lesson()]),  # type: ignore[arg-type]
                storage,  # type: ignore[arg-type]
                FakeQueue(),  # type: ignore[arg-type]
                files=[_upload("ok.pdf", PDF_BYTES), _upload("bad.exe", b"MZ")],
            )
        )
    assert exc.value.status_code == 400
    assert storage.uploaded == []


def test_upload_stores_files_and_queues_searchable_ones() -> None:
    repo = FakeLessonRepo(lessons=[_lesson()])
    storage = FakeStorage()
    queue = FakeQueue()

    result = asyncio.run(
        upload_lesson_files(
            "lesson-1",
            _workspace(),
            _user(),
            _settings(),
            repo,  # type: ignore[arg-type]
            storage,  # type: ignore[arg-type]
            queue,  # type: ignore[arg-type]
            files=[_upload("OODA Loop.pptx", PPTX_BYTES), _upload("legacy.ppt", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest")],
        )
    )

    assert [r.filename for r in result] == ["OODA Loop.pptx", "legacy.ppt"]
    assert [r.index_status for r in result] == ["pending", "skipped"]
    assert [r.position for r in result] == [0, 1]
    assert storage.uploaded[0]["bucket"] == "lesson-files"
    assert storage.uploaded[0]["path"].startswith("the-basic-school/lesson-1/")
    assert storage.uploaded[0]["path"].endswith("-OODA-Loop.pptx")
    assert queue.resources == [result[0].id]


def test_upload_removes_stored_file_when_insert_fails() -> None:
    storage = FakeStorage()
    with pytest.raises(SupabaseRestError):
        asyncio.run(
            upload_lesson_files(
                "lesson-1",
                _workspace(),
                _user(),
                _settings(),
                FakeLessonRepo(lessons=[_lesson()], fail_resource_insert=True),  # type: ignore[arg-type]
                storage,  # type: ignore[arg-type]
                FakeQueue(),  # type: ignore[arg-type]
                files=[_upload("outline.pdf", PDF_BYTES)],
            )
        )
    assert len(storage.uploaded) == 1
    assert storage.deleted == [storage.uploaded[0]["path"]]


def test_delete_resource_removes_storage_object() -> None:
    repo = FakeLessonRepo(lessons=[_lesson()], resources=[_resource()])
    storage = FakeStorage()

    asyncio.run(delete_lesson_resource("lesson-1", "res-1", _workspace(), _settings(), repo, storage))  # type: ignore[arg-type]

    assert storage.deleted_paths == [["the-basic-school/lesson-1/abc-OODA.pptx"]]
    assert repo.deleted_resources == ["res-1"]


def test_delete_lesson_removes_all_files() -> None:
    repo = FakeLessonRepo(
        lessons=[_lesson()],
        resources=[_resource(), _resource(id="res-2", kind="link", url="https://x.example", storage_path=None, filename=None)],
    )
    storage = FakeStorage()

    asyncio.run(delete_lesson("lesson-1", _workspace(), _settings(), repo, storage))  # type: ignore[arg-type]

    assert storage.deleted_paths == [["the-basic-school/lesson-1/abc-OODA.pptx"]]
    assert repo.deleted_lessons == ["lesson-1"]


def test_download_signs_file_with_original_name() -> None:
    repo = FakeLessonRepo(lessons=[_lesson()], resources=[_resource()])
    storage = FakeStorage()

    result = asyncio.run(download_lesson_resource("lesson-1", "res-1", _workspace(), _settings(), repo, storage))  # type: ignore[arg-type]

    assert result.url == "https://signed.example/file"
    assert storage.signed[0]["download_name"] == "OODA.pptx"
    assert storage.signed[0]["bucket"] == "lesson-files"


def test_download_other_workspace_404() -> None:
    repo = FakeLessonRepo(lessons=[_lesson()], resources=[_resource(workspace_id="ws-2")])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(download_lesson_resource("lesson-1", "res-1", _workspace(), _settings(), repo, FakeStorage()))  # type: ignore[arg-type]
    assert exc.value.status_code == 404


def test_reindex_all_queues_lessons_and_searchable_files() -> None:
    repo = FakeLessonRepo(
        lessons=[_lesson(), _lesson(id="lesson-2", title="Cardinal Virtues")],
        resources=[_resource(index_status="failed"), _resource(id="res-2", filename="old.ppt", label="old.ppt")],
    )
    queue = FakeQueue()

    result = asyncio.run(reindex_all_lessons(_workspace(), repo, queue))  # type: ignore[arg-type]

    assert result.lessons == 2
    assert result.files == 1
    assert queue.objective_lessons == ["lesson-1", "lesson-2"]
    assert queue.resources == ["res-1"]
    assert repo.resource_updates == [("res-1", {"index_status": "pending", "index_error": None})]


def test_repository_groups_children_by_lesson() -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.tables: list[str] = []

        async def select_many(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
            self.tables.append(table)
            assert kwargs["filters"] == {"workspace_id": "eq.ws-1"}
            if table == "lessons":
                return [{"id": "a"}, {"id": "b"}]
            if table == "lesson_objectives":
                return [{"id": "o1", "lesson_id": "b"}]
            return [{"id": "r1", "lesson_id": "a"}, {"id": "r2", "lesson_id": "missing"}]

    db = FakeDb()
    rows = asyncio.run(LessonRepository(db).list_with_children("ws-1"))  # type: ignore[arg-type]

    assert db.tables == ["lessons", "lesson_objectives", "lesson_resources"]
    assert [len(row["objectives"]) for row in rows] == [0, 1]
    assert [len(row["resources"]) for row in rows] == [1, 0]
