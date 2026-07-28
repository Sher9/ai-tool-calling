"""Tool registry management (层级 3.1 可视化配置).

Employees list the tools they may use; admins create / update / enable / disable
tools (no code change required — just configure the adapter + JSON-Schema).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.rbac import require_role
from app.core.security import get_current_user
from app.db.models import Tool, User
from app.schemas.tool import ToolCreate, ToolOut, ToolUpdate
from app.tools.registry import invalidate_tools_cache, list_enabled_tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolOut])
async def list_tools(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if user.role == "admin":
        res = await session.execute(select(Tool).order_by(Tool.category, Tool.name))
        return list(res.scalars().all())
    return await list_enabled_tools(session, user)


@router.post("", response_model=ToolOut, dependencies=[Depends(require_role("admin"))])
async def create_tool(payload: ToolCreate, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(Tool).where(Tool.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="工具名已存在")
    tool = Tool(**payload.model_dump())
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    invalidate_tools_cache()
    return tool


@router.put("/{tool_id}", response_model=ToolOut, dependencies=[Depends(require_role("admin"))])
async def update_tool(tool_id: str, payload: ToolUpdate, session: AsyncSession = Depends(get_session)):
    tool = await session.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(tool, k, v)
    await session.commit()
    await session.refresh(tool)
    invalidate_tools_cache()
    return tool


@router.delete("/{tool_id}", dependencies=[Depends(require_role("admin"))])
async def delete_tool(tool_id: str, session: AsyncSession = Depends(get_session)):
    tool = await session.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    await session.delete(tool)
    await session.commit()
    invalidate_tools_cache()
    return {"ok": True}


@router.post("/{tool_id}/toggle", response_model=ToolOut, dependencies=[Depends(require_role("admin"))])
async def toggle_tool(tool_id: str, session: AsyncSession = Depends(get_session)):
    tool = await session.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    tool.enabled = not tool.enabled
    await session.commit()
    await session.refresh(tool)
    invalidate_tools_cache()
    return tool
