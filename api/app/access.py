from fastapi import HTTPException, status

from app.models.auth import CurrentUser

ADMIN_ROLE = "admin"
STUDENT_ROLE = "student"
PLATOON_WORKSPACE_NAME = "The Basic School"


def normalize_access_role(role: str | None) -> str:
    """Map the approved_users.role value onto admin or student.

    `owner` is the pre-platoon value and means admin.
    """
    value = (role or "").strip().lower()
    if value == "owner":
        value = ADMIN_ROLE
    if value not in {ADMIN_ROLE, STUDENT_ROLE}:
        raise ValueError(value or "missing")
    return value


def is_admin(user: CurrentUser) -> bool:
    return user.role == ADMIN_ROLE


def is_platoon_workspace(name: str | None) -> bool:
    return (name or "").strip().casefold() == PLATOON_WORKSPACE_NAME.casefold()


def can_read_library(
    user: CurrentUser,
    workspace_owner_id: str,
    *,
    workspace_name: str | None = None,
) -> bool:
    if user.role == STUDENT_ROLE:
        return is_platoon_workspace(workspace_name)
    return user.role == ADMIN_ROLE and workspace_owner_id == user.id


def forbid_unless_admin(user: CurrentUser) -> None:
    if is_admin(user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Foundry is limited to the Academics officer.",
    )
