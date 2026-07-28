"""Runtime (mutable) configuration flags.

Some settings (e.g. whether external internet tools are enabled) should be
toggleable by an admin at runtime without restarting the service. We back them
with Redis so the value survives restarts, falling back to the .env default.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

_client = None
_cache: dict[str, bool] = {}


def _client_get():
    global _client
    if _client is not None:
        return _client
    try:
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return _client
    except Exception:
        _client = False
        return None


async def external_enabled() -> bool:
    if "external" in _cache:
        return _cache["external"]
    c = _client_get()
    if c:
        try:
            v = await c.get("cfg:external_enabled")
            if v is not None:
                _cache["external"] = v == "1"
                return _cache["external"]
        except Exception:
            pass
    _cache["external"] = settings.EXTERNAL_TOOLS_ENABLED
    return _cache["external"]


async def set_external_enabled(enabled: bool) -> None:
    _cache["external"] = bool(enabled)
    c = _client_get()
    if c:
        try:
            await c.set("cfg:external_enabled", "1" if enabled else "0")
        except Exception:
            pass
