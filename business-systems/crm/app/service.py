"""CRM 业务逻辑：真实 DB 操作 + 行级权限（销售仅看自己客户，管理员看全部）。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select

from app.auth import Actor
from app.db import async_session_maker
from app.models import CrmCustomer, CrmDeal

CRM_ROLES = {"admin", "sales"}


def _cust(c: CrmCustomer) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "industry": c.industry,
        "stage": c.stage,
        "owner": c.owner,
        "amount": float(c.amount),
        "contact_name": c.contact_name,
        "contact_phone": c.contact_phone,
        "contact_email": c.contact_email,
        "remark": c.remark,
    }


async def crm_search(keyword: str, actor: Actor) -> dict:
    """返回 {"items": [...], "message": str|None}。

    - 角色不在 CRM_ROLES（admin/sales）内：明确告知无权限，而非静默返回空列表；
    - 角色合法但当前账号名下无客户：明确告知“无归属客户”，便于排查 owner 不匹配问题。
    """
    if actor.role not in CRM_ROLES:
        return {
            "items": [],
            "message": f"当前角色（{actor.role}）无 CRM 客户查看权限；CRM 仅对 sales/admin 开放，请切换销售或管理员账号。",
        }
    async with async_session_maker() as s:
        stmt = select(CrmCustomer)
        if actor.role != "admin":
            stmt = stmt.where(CrmCustomer.owner == actor.username)
        if keyword:
            stmt = stmt.where(CrmCustomer.name.ilike(f"%{keyword}%"))
        rows = (await s.execute(stmt)).scalars().all()
        items = [_cust(c) for c in rows]
        if not items and actor.role != "admin":
            return {
                "items": [],
                "message": f"CRM 中暂无归属当前账号（{actor.username}）的客户记录。"
                f"（演示数据 owner 为 ivan/alice/bob，请用这些账号登录，或联系管理员。)",
            }
        return {"items": items, "message": None}


async def crm_customer(cid: str, actor: Actor) -> Optional[dict]:
    async with async_session_maker() as s:
        c = await s.get(CrmCustomer, cid)
        if not c:
            return None
        if actor.role != "admin" and c.owner != actor.username:
            return None
        return _cust(c)


async def crm_deals(actor: Actor) -> list[dict]:
    async with async_session_maker() as s:
        stmt = select(CrmDeal)
        if actor.role != "admin":
            stmt = stmt.where(CrmDeal.owner == actor.username)
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "id": d.id,
                "customer_id": d.customer_id,
                "title": d.title,
                "amount": float(d.amount),
                "stage": d.stage,
                "expected_close_date": str(d.expected_close_date) if d.expected_close_date else "",
                "owner": d.owner,
            }
            for d in rows
        ]


async def crm_stats(actor: Actor) -> list[dict]:
    if actor.role not in CRM_ROLES:
        return []
    async with async_session_maker() as s:
        stmt = select(
            CrmCustomer.stage,
            func.coalesce(func.sum(CrmCustomer.amount), 0),
            func.count(),
        )
        if actor.role != "admin":
            stmt = stmt.where(CrmCustomer.owner == actor.username)
        stmt = stmt.group_by(CrmCustomer.stage)
        rows = (await s.execute(stmt)).all()
        return [
            {"stage": stage, "amount": float(amount), "count": int(cnt)}
            for stage, amount, cnt in rows
        ]
