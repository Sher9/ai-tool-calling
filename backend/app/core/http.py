"""Async HTTP helpers for real tool integrations.

All tool adapters that talk to external/ internal systems should go through
these helpers so we get a consistent timeout, bearer auth, and JSON handling.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

DEFAULT_TIMEOUT = 15.0


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token and token != "EMPTY" else {}


async def aget(
    url: str,
    *,
    token: str = "",
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """GET and return parsed JSON (or raw text when not JSON)."""
    h = {**(headers or {}), **_auth(token)}
    async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=h)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return resp.text


async def apost(
    url: str,
    *,
    token: str = "",
    json: Optional[dict] = None,
    data: Optional[dict] = None,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """POST and return parsed JSON (or raw text when not JSON)."""
    h = {**(headers or {}), **_auth(token)}
    async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True) as client:
        resp = await client.post(url, json=json, data=data, params=params, headers=h)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return resp.text
