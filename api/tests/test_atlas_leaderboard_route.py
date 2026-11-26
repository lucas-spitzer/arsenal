from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import require_approved_user
from app.dependencies.services import get_atlas_service, get_workspace_repository
from app.models.atlas import LeaderboardEntry, LeaderboardResponse
from app.models.auth import CurrentUser
from app.routers import atlas

WORKSPACE = {
    "id": "ws-1",
    "owner_id": "admin-1",
    "name": "The Basic School",
    "slug": "tbs",
    "description": None,
    "status": "active",
    "created_at": datetime(2026, 11, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 11, 1, tzinfo=UTC),
}


class _Workspaces:
    async def get_for_owner(self, workspace_id: str, owner_id: str) -> dict[str, Any] | None:
        return WORKSPACE if owner_id == WORKSPACE["owner_id"] else None

    async def get(self, workspace_id: str) -> dict[str, Any] | None:
        return WORKSPACE


class _Atlas:
    def __init__(self) -> None:
        self.ap = 10

    async def leaderboard(self, *, user: CurrentUser, workspace_id: str) -> LeaderboardResponse:
        return LeaderboardResponse(
            platoon_total_ap=self.ap,
            platoon_goal=None,
            ends_at=datetime(2026, 12, 1, 3, tzinfo=UTC),
            finalized=False,
            student_access=True,
            entries=[
                LeaderboardEntry(
                    rank=1, user_id="student-1", name="Student", lifetime_ap=self.ap, concepts_mastered=0, accuracy=None
                )
            ],
        )


def _client(user: CurrentUser, service: _Atlas) -> TestClient:
    app = FastAPI()
    app.include_router(atlas.router)
    app.dependency_overrides[require_approved_user] = lambda: user
    app.dependency_overrides[get_workspace_repository] = _Workspaces
    app.dependency_overrides[get_atlas_service] = lambda: service
    return TestClient(app)


@pytest.mark.parametrize(
    "user",
    [
        CurrentUser(id="admin-1", email="admin@example.com", role="admin"),
        CurrentUser(id="student-1", email="student@example.com", role="student"),
    ],
)
def test_leaderboard_is_never_cached_and_reflects_new_points(user: CurrentUser) -> None:
    service = _Atlas()
    client = _client(user, service)

    first = client.get("/workspaces/ws-1/atlas/leaderboard")
    service.ap = 25
    second = client.get("/workspaces/ws-1/atlas/leaderboard")

    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["entries"][0]["lifetime_ap"] == 10
    assert second.headers["cache-control"] == "no-store"
    assert second.json()["entries"][0]["lifetime_ap"] == 25
