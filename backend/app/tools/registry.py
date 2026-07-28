"""Central tool registry & dispatch (层级 3.1 工具注册中心)."""
from __future__ import annotations

from typing import Iterable

import time

from sqlalchemy import select

from app.config import settings
from app.core.masking import mask_text
from app.core.rbac import ADMIN_ROLE
from app.core.runtime_cfg import external_enabled
from app.db.models import Tool, User
from app.tools.adapters import business, compute, custom, dev, external, general, gitweekly, knowledge, office
from app.tools.base import ToolContext, ToolResult, fail, function_schema

# Combined adapter registry: adapter-key -> async handler
_ADAPTER_MAP: dict = {}
for _mod in (office, dev, business, compute, custom, external, general, knowledge, gitweekly):
    _ADAPTER_MAP.update(getattr(_mod, "ADAPTERS", {}))


def get_adapter(name: str):
    return _ADAPTER_MAP.get(name)


async def dispatch(tool: Tool, args: dict, ctx: ToolContext, session) -> ToolResult:
    """Run a tool with full safety & permission checks, then mask output."""
    if not tool.enabled:
        return fail(f"工具「{tool.name}」已停用")
    if tool.requires_internet and not await external_enabled():
        return fail("外网检索工具当前未开启（需管理员在后台启用）")
    if ctx.role != ADMIN_ROLE and tool.allowed_roles and ctx.role not in tool.allowed_roles:
        return fail(f"当前角色({ctx.role})无权使用工具「{tool.display_name or tool.name}」")
    handler = _ADAPTER_MAP.get(tool.adapter) or _ADAPTER_MAP.get(tool.name)
    if not handler:
        return fail(f"工具「{tool.name}」缺少适配器实现")
    try:
        result = await handler(args, ctx)
    except Exception as e:  # noqa: BLE001
        return fail(f"工具执行异常：{type(e).__name__}: {e}")

    if result.ok and tool.mask_sensitive and not ctx.raw:
        result = _mask_result(result)
    return result


def _mask_result(result: ToolResult) -> ToolResult:
    if result.kind == "text":
        result.text = mask_text(result.text)
    elif result.kind == "table":
        rows = [[mask_text(str(c)) if isinstance(c, str) else c for c in row]
                for row in result.table.get("rows", [])]
        result.table = {**result.table, "rows": rows}
    return result


# 工具列表是低频变更的静态数据：进程内缓存（按角色+外网开关分桶，短 TTL），
# 避免每个请求都查一次 DB。工具启用/停用最多 60s 后生效。
_TOOLS_CACHE: dict[str, tuple[float, list[Tool]]] = {}
_TOOLS_TTL = 60.0


def invalidate_tools_cache() -> None:
    """工具启用/停用变更后调用，立即失效缓存。"""
    _TOOLS_CACHE.clear()


async def list_enabled_tools(session, user: User) -> list[Tool]:
    ext = await external_enabled()
    key = f"{user.role}:{ext}"
    cached = _TOOLS_CACHE.get(key)
    if cached is not None and (time.monotonic() - cached[0]) < _TOOLS_TTL:
        return cached[1]
    stmt = select(Tool).where(Tool.enabled.is_(True))
    res = await session.execute(stmt)
    tools = res.scalars().all()
    if user.role == ADMIN_ROLE:
        out = [t for t in tools if (not t.requires_internet or ext)]
    else:
        out = [t for t in tools if (not t.allowed_roles or user.role in t.allowed_roles)
               and (not t.requires_internet or ext)]
    _TOOLS_CACHE[key] = (time.monotonic(), out)
    return out


def build_function_schemas(tools: Iterable[Tool]) -> list[dict]:
    return [function_schema(t) for t in tools]
