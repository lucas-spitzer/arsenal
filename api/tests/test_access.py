import asyncio

import pytest
from fastapi import HTTPException

from app.access import can_read_library, normalize_access_role
from app.dependencies.auth import require_admin
from app.models.auth import CurrentUser


def test_owner_role_maps_to_admin() -> None:
    assert normalize_access_role("owner") == "admin"
    assert normalize_access_role(" Admin ") == "admin"
    assert normalize_access_role("student") == "student"


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_access_role("viewer")


def test_student_reads_the_platoon_library() -> None:
    student = CurrentUser(id="student-1", email="student@example.com", role="student")
    admin = CurrentUser(id="admin-1", email="admin@example.com", role="admin")

    assert can_read_library(
        student,
        "admin-1",
        workspace_name="The Basic School",
    ) is True
    assert can_read_library(student, "admin-1", workspace_name="Personal notes") is False
    assert can_read_library(admin, "admin-1") is True
    assert can_read_library(admin, "someone-else") is False


def test_require_admin_rejects_a_student() -> None:
    student = CurrentUser(id="student-1", email="student@example.com", role="student")

    with pytest.raises(HTTPException) as raised:
        asyncio.run(require_admin(student))

    assert raised.value.status_code == 403


def test_require_admin_accepts_the_academics_officer() -> None:
    admin = CurrentUser(id="admin-1", email="admin@example.com", role="admin")

    assert asyncio.run(require_admin(admin)) == admin
