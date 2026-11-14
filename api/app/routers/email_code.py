from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.email_code_limit import allow_email_code
from app.services.supabase import (
    SupabaseApprovalError,
    SupabaseEmailCodeError,
    SupabaseRequestError,
    SupabaseService,
    SupabaseUserNotApprovedError,
)

router = APIRouter(tags=["auth"])


class EmailCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


def _sign_in_email(value: str) -> str:
    email = value.strip()
    local, separator, domain = email.rpartition("@")
    if (
        not separator
        or not local
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or any(character.isspace() for character in email)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid email address.",
        )
    return email


def _client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/auth/email-code", status_code=status.HTTP_204_NO_CONTENT)
async def send_email_code(
    payload: EmailCodeRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    email = _sign_in_email(payload.email)
    if not allow_email_code(email, _client_address(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Wait a minute, then request another code.",
        )

    supabase = SupabaseService(settings)
    try:
        await supabase.send_email_code(email)
    except SupabaseUserNotApprovedError:
        return None
    except SupabaseEmailCodeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
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
    return None
