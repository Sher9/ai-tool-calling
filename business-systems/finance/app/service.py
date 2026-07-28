"""财务 ERP 业务逻辑：真实 DB 操作 + 角色权限（仅财务/管理员可访问，敏感字段受控）。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select

from app.auth import Actor
from app.db import async_session_maker
from app.models import FinExpense, FinInvoice, FinRevenue

FINANCE_ROLES = {"admin", "finance"}


def _check(actor: Actor) -> bool:
    return actor.role in FINANCE_ROLES


def _invoice(inv: FinInvoice, sensitive: bool) -> dict:
    d = {
        "id": inv.id,
        "invoice_no": inv.invoice_no,
        "supplier": inv.supplier,
        "buyer": inv.buyer,
        "amount": float(inv.amount),
        "issue_date": str(inv.issue_date) if inv.issue_date else "",
        "status": inv.status,
    }
    if sensitive:
        d.update(tax_no=inv.tax_no, bank_account=inv.bank_account)
    return d


async def finance_invoices(actor: Actor, supplier: str) -> list[dict]:
    if not _check(actor):
        return []
    async with async_session_maker() as s:
        stmt = select(FinInvoice)
        if supplier:
            stmt = stmt.where(FinInvoice.supplier.ilike(f"%{supplier}%"))
        rows = (await s.execute(stmt)).scalars().all()
        return [_invoice(i, sensitive=True) for i in rows]


async def finance_revenue(actor: Actor, month: str) -> list[dict]:
    if not _check(actor):
        return []
    async with async_session_maker() as s:
        stmt = select(FinRevenue)
        if month:
            stmt = stmt.where(FinRevenue.month == month)
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "month": r.month,
                "revenue": float(r.revenue),
                "cost": float(r.cost),
                "profit": float(r.profit),
                "note": r.note,
            }
            for r in rows
        ]


async def finance_expenses(actor: Actor, category: str) -> list[dict]:
    if not _check(actor):
        return []
    async with async_session_maker() as s:
        stmt = select(FinExpense)
        if category:
            stmt = stmt.where(FinExpense.category == category)
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "id": e.id,
                "category": e.category,
                "applicant": e.applicant,
                "amount": float(e.amount),
                "occur_date": str(e.occur_date) if e.occur_date else "",
                "status": e.status,
                "remark": e.remark,
            }
            for e in rows
        ]


async def finance_summary(actor: Actor) -> Optional[dict]:
    if not _check(actor):
        return None
    async with async_session_maker() as s:
        total_invoice = (await s.execute(
            select(func.coalesce(func.sum(FinInvoice.amount), 0))
        )).scalar_one()
        total_expense = (await s.execute(
            select(func.coalesce(func.sum(FinExpense.amount), 0))
        )).scalar_one()
        rev = (await s.execute(select(func.coalesce(func.sum(FinRevenue.revenue), 0)))).scalar_one()
        cost = (await s.execute(select(func.coalesce(func.sum(FinRevenue.cost), 0)))).scalar_one()
        profit = (await s.execute(select(func.coalesce(func.sum(FinRevenue.profit), 0)))).scalar_one()
        return {
            "total_invoice": float(total_invoice),
            "total_expense": float(total_expense),
            "total_revenue": float(rev),
            "total_cost": float(cost),
            "total_profit": float(profit),
        }
