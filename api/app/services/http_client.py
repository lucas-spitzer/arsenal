import asyncio

import httpx

_client: httpx.AsyncClient | None = None
_loop: asyncio.AbstractEventLoop | None = None


def shared_client() -> httpx.AsyncClient:
    """One keep-alive client per event loop, so Supabase calls skip a fresh TLS handshake.

    A client is bound to the loop that opened its connections, so a new loop gets a new client.
    """
    global _client, _loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _loop is not loop:
        _client = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
        _loop = loop
    return _client


async def close_shared_client() -> None:
    global _client, _loop
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
    _loop = None
