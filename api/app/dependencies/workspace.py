from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.access import ADMIN_ROLE, STUDENT_ROLE, is_platoon_workspace
from app.dependencies.auth import require_approved_user
from app.dependencies.services import get_workspace_repository
from app.models.auth import CurrentUser
from app.models.workspace import WorkspaceResponse
from app.repositories.workspaces import WorkspaceRepository


async def require_workspace(
    workspace_id: str,
    user: Annotated[CurrentUser, Depends(require_approved_user)],
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceResponse:
    if user.role == ADMIN_ROLE:
        workspace = await workspaces.get_for_owner(workspace_id, user.id)
    elif user.role == STUDENT_ROLE:
        workspace = await workspaces.get(workspace_id)
        if workspace is not None and not is_platoon_workspace(str(workspace.get("name") or "")):
            workspace = None
    else:
        workspace = None

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    return WorkspaceResponse.model_validate(workspace)
