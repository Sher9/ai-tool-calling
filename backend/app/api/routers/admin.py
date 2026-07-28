"""Admin console API (层级 1 管理员后台): 权限/审计/模型配置/告警."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.audit import write_audit
from app.core.rbac import require_role
from app.core.runtime_cfg import external_enabled, set_external_enabled
from app.core.security import get_current_user, hash_password
from app.db.models import AuditLog, Conversation, PromptTemplate, TaskRecord, Tool, User
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit")
async def audit_logs(
    action: str | None = None,
    sensitive: bool | None = None,
    limit: int = Query(100, le=500),
    user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if sensitive is not None:
        stmt = stmt.where(AuditLog.sensitive.is_(sensitive))
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    res = await session.execute(stmt)
    return [
        {
            "id": a.id, "user_id": a.user_id, "username": a.username, "action": a.action,
            "resource": a.resource, "detail": a.detail, "ip": a.ip, "sensitive": a.sensitive,
            "created_at": a.created_at.isoformat(),
        }
        for a in res.scalars().all()
    ]


@router.get("/audit/alerts")
async def sensitive_alerts(
    user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(AuditLog).where(AuditLog.sensitive.is_(True)).order_by(AuditLog.created_at.desc()).limit(100)
    res = await session.execute(stmt)
    return [
        {"username": a.username, "resource": a.resource, "detail": a.detail, "created_at": a.created_at.isoformat()}
        for a in res.scalars().all()
    ]


@router.get("/users", response_model=list[UserOut])
async def list_users(user: User = Depends(require_role("admin")), session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(User).order_by(User.created_at))
    return list(res.scalars().all())


@router.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate, user: User = Depends(require_role("admin")),
                      session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(User).where(User.username == payload.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    new_user = User(
        username=payload.username,
        display_name=payload.display_name or payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        department=payload.department,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    await write_audit(session, user_id=user.id, username=user.username, action="admin_op",
                      resource="user.create", detail={"target": payload.username})
    return new_user


@router.get("/prompts")
async def list_prompts(user: User = Depends(require_role("admin")), session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(PromptTemplate))
    return [{"key": p.key, "title": p.title, "content": p.content, "updated_at": p.updated_at.isoformat()}
            for p in res.scalars().all()]


@router.put("/prompts/{key}")
async def update_prompt(key: str, body: dict, user: User = Depends(require_role("admin")),
                        session: AsyncSession = Depends(get_session)):
    prompt = await session.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    p = prompt.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="提示词模板不存在")
    p.content = body.get("content", p.content)
    p.title = body.get("title", p.title)
    await session.commit()
    await session.refresh(p)
    return {"ok": True, "key": p.key}


@router.get("/settings")
async def settings_view(user: User = Depends(require_role("admin")), session: AsyncSession = Depends(get_session)):
    from app.config import settings

    return {
        "external_tools_enabled": await external_enabled(),
        "mock_llm": settings.MOCK_LLM,
        "env_external_default": settings.EXTERNAL_TOOLS_ENABLED,
    }


@router.post("/settings/external")
async def set_external(body: dict, user: User = Depends(require_role("admin")),
                       session: AsyncSession = Depends(get_session)):
    enabled = bool(body.get("enabled", False))
    await set_external_enabled(enabled)
    await write_audit(session, user_id=user.id, username=user.username, action="admin_op",
                      resource="external.toggle", detail={"enabled": enabled})
    return {"external_tools_enabled": enabled}


@router.get("/stats")
async def dashboard_stats(user: User = Depends(require_role("admin")), session: AsyncSession = Depends(get_session)):
    async def count(model, *where):
        stmt = select(func.count()).select_from(model)
        for w in where:
            stmt = stmt.where(w)
        return (await session.execute(stmt)).scalar_one()

    return {
        "users": await count(User),
        "tools": await count(Tool),
        "tools_enabled": await count(Tool, Tool.enabled.is_(True)),
        "conversations": await count(Conversation),
        "tasks": await count(TaskRecord),
        "audit": await count(AuditLog),
        "sensitive_alerts": await count(AuditLog, AuditLog.sensitive.is_(True)),
    }
