from fastapi import HTTPException, status

from app.models.auth import CurrentUser

ADMIN_ROLE = "admin"
STUDENT_ROLE = "student"
OBSERVER_ROLE = "observer"
PLATOON_WORKSPACE_NAME = "The Basic School"
_ACCESS_ROLES = {ADMIN_ROLE, STUDENT_ROLE, OBSERVER_ROLE}
_PLATOON_READER_ROLES = {STUDENT_ROLE, OBSERVER_ROLE}


def normalize_access_role(role: str | None) -> str:
    """Map the approved_users.role value onto admin, student, or observer.

    `owner` is the pre-platoon value and means admin.
    """
    value = (role or "").strip().lower()
    if value == "owner":
        value = ADMIN_ROLE
    if value not in _ACCESS_ROLES:
        raise ValueError(value or "missing")
    return value


def is_admin(user: CurrentUser) -> bool:
    return user.role == ADMIN_ROLE


def is_platoon_reader(user: CurrentUser) -> bool:
    return user.role in _PLATOON_READER_ROLES


def is_platoon_workspace(name: str | None) -> bool:
    return (name or "").strip().casefold() == PLATOON_WORKSPACE_NAME.casefold()


def counts_on_leaderboard(role: str | None) -> bool:
    """Observers study Academy but do not appear on standings."""
    try:
        return normalize_access_role(role) != OBSERVER_ROLE
    except ValueError:
        return False


def can_read_library(
    user: CurrentUser,
    workspace_owner_id: str,
    *,
    workspace_name: str | None = None,
) -> bool:
    if is_platoon_reader(user):
        return is_platoon_workspace(workspace_name)
    return user.role == ADMIN_ROLE and workspace_owner_id == user.id


def forbid_unless_admin(user: CurrentUser) -> None:
    if is_admin(user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Foundry is limited to the Academics officer.",
    )
