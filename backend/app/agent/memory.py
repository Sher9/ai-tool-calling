"""Memory management (层级 3.4).

- Short-term session memory: Redis list per conversation (auto-trimmed).
- Long-term user memory: Redis hash of frequent commands / preferences.
Falls back to in-process storage when Redis is unavailable so dev works.
"""
from __future__ import annotations

import json

import redis.asyncio as aioredis

from app.config import settings

_client = None
_local_hist: dict[str, list[str]] = {}
_local_pref: dict[str, dict] = {}


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


async def load_history(conversation_id: str, limit: int = 20) -> list[dict]:
    c = _client_get()
    if c:
        try:
            items = await c.lrange(f"hist:{conversation_id}", -limit, -1)
            return [json.loads(i) for i in items]
        except Exception:
            pass
    return [json.loads(i) for i in _local_hist.get(conversation_id, [])][-limit:]


async def append_message(conversation_id: str, role: str, content: str) -> None:
    item = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    c = _client_get()
    if c:
        try:
            await c.rpush(f"hist:{conversation_id}", item)
            await c.ltrim(f"hist:{conversation_id}", -50, 50)
            return
        except Exception:
            pass
    _local_hist.setdefault(conversation_id, []).append(item)
    _local_hist[conversation_id] = _local_hist[conversation_id][-50:]


async def record_preference(user_id: str, command: str) -> None:
    """Track the user's most frequent commands to personalize later answers."""
    cmd = command.strip()
    if len(cmd) < 4:
        return
    c = _client_get()
    key = f"pref:{user_id}"
    if c:
        try:
            await c.hincrby(key, cmd, 1)
            await c.expire(key, 60 * 60 * 24 * 30)
            return
        except Exception:
            pass
    prefs = _local_pref.setdefault(user_id, {})
    prefs[cmd] = prefs.get(cmd, 0) + 1


async def top_preferences(user_id: str, n: int = 5) -> list[str]:
    c = _client_get()
    if c:
        try:
            raw = await c.hgetall(f"pref:{user_id}")
            return [k for k, _ in sorted(raw.items(), key=lambda x: -int(x[1]))[:n]]
        except Exception:
            pass
    prefs = _local_pref.get(user_id, {})
    return [k for k, _ in sorted(prefs.items(), key=lambda x: -x[1])[:n]]
