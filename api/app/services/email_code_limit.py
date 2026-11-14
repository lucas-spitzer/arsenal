"""In-process cap for POST /auth/email-code.

Each API process keeps its own counters. They are not shared across processes
or Vercel instances.
"""

from __future__ import annotations

import time

WINDOW_SECONDS = 10 * 60
EMAIL_LIMIT = 5
CLIENT_LIMIT = 20

_email_hits: dict[str, list[float]] = {}
_client_hits: dict[str, list[float]] = {}


def clear_email_code_limits() -> None:
    _email_hits.clear()
    _client_hits.clear()


def allow_email_code(email: str, client: str, *, now: float | None = None) -> bool:
    moment = time.monotonic() if now is None else now
    _prune(_email_hits, moment)
    _prune(_client_hits, moment)
    email_key = email.casefold()
    email_recent = _email_hits.get(email_key, [])
    client_recent = _client_hits.get(client, [])
    if len(email_recent) >= EMAIL_LIMIT or len(client_recent) >= CLIENT_LIMIT:
        return False
    _email_hits[email_key] = [*email_recent, moment]
    _client_hits[client] = [*client_recent, moment]
    return True


def _prune(store: dict[str, list[float]], now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    stale = [key for key, hits in store.items() if all(hit < cutoff for hit in hits)]
    for key in stale:
        del store[key]
    for key, hits in store.items():
        store[key] = [hit for hit in hits if hit >= cutoff]
