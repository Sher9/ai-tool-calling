"""Audit logging (操作审计).

Every tool call, login, admin operation and sensitive-data access is recorded
into `audit_logs`. Sensitive events also surface on the admin alert panel.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    user_id: str = "",
    username: str = "",
    action: str,
    resource: str = "",
    detail: dict | None = None,
    ip: str = "",
    sensitive: bool = False,
    commit: bool = True,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        resource=resource,
        detail=detail or {},
        ip=ip,
        sensitive=sensitive,
    )
    session.add(log)
    if commit:
        await session.commit()
        await session.refresh(log)
    return log
