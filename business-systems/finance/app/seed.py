"""财务 ERP 演示数据（幂等写入）。"""
from __future__ import annotations

from app.db import async_session_maker
from app.models import FinExpense, FinInvoice, FinRevenue

INVOICES = [
    dict(id="inv-001", invoice_no="FP2026070001", supplier="上海恒昇制造", buyer="我方",
         amount=860000, tax_no="91310000MA1FL9X001", bank_account="6222021234567890123",
         issue_date="2026-07-05", status="待付款"),
    dict(id="inv-002", invoice_no="FP2026070002", supplier="深圳锐驰物流", buyer="我方",
         amount=540000, tax_no="91440300MA5ET2X002", bank_account="6222022234567890124",
         issue_date="2026-07-12", status="已付款"),
]

REVENUE = [
    dict(id="rev-2026-06", month="2026-06", revenue=3200000, cost=1900000, profit=1300000, note="Q2 收尾"),
    dict(id="rev-2026-07", month="2026-07", revenue=2600000, cost=1500000, profit=1100000, note="夏季促销"),
]

EXPENSES = [
    dict(id="exp-001", category="差旅", applicant="bob", amount=4800, occur_date="2026-07-10",
         status="已报销", remark="客户拜访"),
    dict(id="exp-002", category="采购", applicant="carol", amount=12500, occur_date="2026-07-15",
         status="待报销", remark="研发设备"),
    dict(id="exp-003", category="招待", applicant="alice", amount=3200, occur_date="2026-07-18",
         status="待报销", remark="商务宴请"),
]


async def seed(session) -> None:
    for i in INVOICES:
        if not await session.get(FinInvoice, i["id"]):
            session.add(FinInvoice(**i))
    for r in REVENUE:
        if not await session.get(FinRevenue, r["id"]):
            session.add(FinRevenue(**r))
    for e in EXPENSES:
        if not await session.get(FinExpense, e["id"]):
            session.add(FinExpense(**e))
    await session.commit()
