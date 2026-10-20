from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.access import forbid_unless_admin
from app.config import Settings, get_settings
from app.models.auth import CurrentUser
from app.services.supabase import (
    SupabaseApprovalError,
    SupabaseAuthError,
    SupabaseRequestError,
    SupabaseService,
    SupabaseUserNotApprovedError,
)


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header.",
        )

    return token


async def require_approved_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    token = extract_bearer_token(authorization)
    supabase = SupabaseService(settings)

    try:
        return await supabase.get_current_user(token)
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Supabase session.",
        ) from exc
    except SupabaseUserNotApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not approved for Arsenal access.",
        ) from exc
    except SupabaseApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Arsenal could not complete the approval lookup.",
        ) from exc
    except SupabaseRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Arsenal could not reach Supabase.",
        ) from exc


async def require_admin(
    user: Annotated[CurrentUser, Depends(require_approved_user)],
) -> CurrentUser:
    forbid_unless_admin(user)
    return user
