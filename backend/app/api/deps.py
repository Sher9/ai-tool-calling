"""Shared API dependencies."""
from __future__ import annotations

from fastapi import Request

from app.core.security import get_current_user
from app.db.base import get_session


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


__all__ = ["get_session", "get_current_user", "client_ip"]
