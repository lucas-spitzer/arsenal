import hashlib
import time
from typing import Any

import httpx

from app.access import normalize_access_role
from app.config import Settings
from app.models.auth import CurrentUser
from app.services.http_client import shared_client

USER_CACHE_SECONDS = 60
USER_CACHE_LIMIT = 512
_user_cache: dict[str, tuple[float, CurrentUser]] = {}


def _token_key(access_token: str) -> str:
    return hashlib.sha256(access_token.encode()).hexdigest()


def clear_user_cache() -> None:
    _user_cache.clear()


class SupabaseAuthError(Exception):
    """Raised when Supabase cannot validate the presented user token."""


class SupabaseApprovalError(Exception):
    """Raised when Arsenal cannot complete the approval lookup."""


class SupabaseRequestError(Exception):
    """Raised when Supabase cannot be reached."""


class SupabaseUserNotApprovedError(Exception):
    """Raised when a valid Supabase user is not approved for Arsenal."""


class SupabaseEmailCodeError(Exception):
    """Raised when Supabase Auth refuses to send a sign-in code."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class SupabaseService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_current_user(self, access_token: str) -> CurrentUser:
        """Successful lookups are remembered briefly, so a revoked approval blocks within a minute."""
        key = _token_key(access_token)
        now = time.monotonic()
        cached = _user_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        current = await self._lookup_current_user(access_token)
        if len(_user_cache) >= USER_CACHE_LIMIT:
            for stale in [k for k, (expires, _) in _user_cache.items() if expires <= now]:
                del _user_cache[stale]
            if len(_user_cache) >= USER_CACHE_LIMIT:
                _user_cache.pop(next(iter(_user_cache)))
        _user_cache[key] = (now + USER_CACHE_SECONDS, current)
        return current

    async def _lookup_current_user(self, access_token: str) -> CurrentUser:
        user = await self._get_supabase_user(access_token)
        user_id = user.get("id")
        email = user.get("email")

        if not isinstance(user_id, str) or not isinstance(email, str):
            raise SupabaseAuthError("Supabase user payload is missing required claims.")

        approved_user = await self._get_approved_user(email)

        try:
            role = normalize_access_role(
                approved_user.get("role") if isinstance(approved_user.get("role"), str) else None,
            )
        except ValueError as exc:
            raise SupabaseUserNotApprovedError(
                "This account is not approved for Arsenal access.",
            ) from exc

        name = approved_user.get("name")
        rank = approved_user.get("rank")

        return CurrentUser(
            id=user_id,
            email=email,
            role=role,
            name=name if isinstance(name, str) else None,
            rank=rank if isinstance(rank, str) else None,
        )

    async def send_email_code(self, email: str) -> None:
        """Mail a sign-in code only when the address is an active approved user."""
        await self._get_approved_user(email.strip())
        await self._send_email_otp(email.strip())

    async def _get_supabase_user(self, access_token: str) -> dict[str, Any]:
        try:
            response = await shared_client().get(
                f"{self.settings.supabase_url}/auth/v1/user",
                headers={
                    "apikey": self.settings.supabase_publishable_key,
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=10,
            )
        except httpx.HTTPError as exc:
            raise SupabaseRequestError("Supabase Auth could not be reached.") from exc

        if response.status_code != 200:
            raise SupabaseAuthError("Invalid or expired Supabase session.")

        return response.json()

    async def _get_approved_user(self, email: str) -> dict[str, Any]:
        try:
            response = await shared_client().get(
                f"{self.settings.supabase_url}/rest/v1/approved_users",
                headers={
                    "apikey": self.settings.supabase_service_role_key,
                    "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
                    "Accept": "application/json",
                },
                params={
                    "select": "email,role,is_active,name,rank",
                    "email": f"eq.{email}",
                    "is_active": "eq.true",
                    "limit": "1",
                },
                timeout=10,
            )
        except httpx.HTTPError as exc:
            raise SupabaseRequestError("Supabase REST could not be reached.") from exc

        if response.status_code != 200:
            raise SupabaseApprovalError("Approval lookup failed.")

        approved_users = response.json()

        if not approved_users:
            raise SupabaseUserNotApprovedError(
                "This account is not approved for Arsenal access.",
            )

        approved_user = approved_users[0]

        if not approved_user.get("is_active"):
            raise SupabaseUserNotApprovedError(
                "This account is not approved for Arsenal access.",
            )

        return approved_user

    async def _send_email_otp(self, email: str) -> None:
        try:
            response = await shared_client().post(
                f"{self.settings.supabase_url}/auth/v1/otp",
                headers={
                    "apikey": self.settings.supabase_publishable_key,
                    "Authorization": f"Bearer {self.settings.supabase_publishable_key}",
                    "Content-Type": "application/json",
                },
                json={"email": email, "create_user": True},
                timeout=10,
            )
        except httpx.HTTPError as exc:
            raise SupabaseRequestError("Supabase Auth could not be reached.") from exc

        if response.status_code == 200:
            return

        if response.status_code == 429:
            raise SupabaseEmailCodeError(
                "Wait a minute, then request another code.",
                status_code=429,
            )

        raise SupabaseEmailCodeError("Arsenal could not send a sign-in code.")
