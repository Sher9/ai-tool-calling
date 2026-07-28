"""BIZ 业务逻辑：库存 / 产品参数 / 资源申请 / 报价单。真实 DB 操作。"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select

from app.auth import Actor
from app.db import async_session_maker
from app.models import (
    CalendarEvent, InventoryItem, ProductParam, Quote, QuoteItem,
)


# ---------------- 库存 ----------------
async def inventory_search(keyword: str, actor: Actor) -> list[dict]:
    async with async_session_maker() as s:
        stmt = select(InventoryItem)
        if keyword:
            stmt = stmt.where(InventoryItem.name.ilike(f"%{keyword}%"))
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "sku": r.sku,
                "name": r.name,
                "category": r.category,
                "stock": r.stock,
                "warehouse": r.warehouse,
                "price": float(r.price),
            }
            for r in rows
        ]


# ---------------- 产品参数 ----------------
async def product_param(model: str, actor: Actor) -> dict | None:
    async with async_session_maker() as s:
        r = await s.get(ProductParam, model)
        if not r:
            return None
        return {
            "model": r.model,
            "name": r.name,
            "cpu": r.cpu,
            "memory": r.memory,
            "disk": r.disk,
            "price": float(r.price),
            "warranty": r.warranty,
            "remark": r.remark,
        }


# ---------------- 报价单 ----------------
async def quote_generate(items: list[dict], owner: str, customer: str, actor: Actor) -> dict:
    qid = f"quote-{uuid.uuid4().hex[:8]}"
    total = 0.0
    async with async_session_maker() as s:
        quote = Quote(id=qid, owner=owner, customer=customer, total=0)
        s.add(quote)
        await s.flush()
        for idx, it in enumerate(items):
            qty = int(it.get("qty", 1))
            price = float(it.get("price", 0))
            subtotal = qty * price
            total += subtotal
            s.add(QuoteItem(
                id=f"{qid}-{idx+1}", quote_id=qid,
                name=it.get("name", ""), qty=qty, price=price, subtotal=subtotal,
            ))
        quote.total = total
        await s.commit()
        return {
            "quote_id": qid,
            "owner": owner,
            "customer": customer,
            "items": [
                {"name": it.get("name", ""), "qty": int(it.get("qty", 1)),
                 "price": float(it.get("price", 0)),
                 "subtotal": int(it.get("qty", 1)) * float(it.get("price", 0))}
                for it in items
            ],
            "total": total,
            "status": "已生成",
        }


# ---------------- 日历日程 ----------------
async def calendar_events(event_date: date, owner: str) -> list[dict]:
    async with async_session_maker() as s:
        stmt = select(CalendarEvent).where(CalendarEvent.event_date == event_date)
        if owner and owner != "anonymous":
            stmt = stmt.where(CalendarEvent.owner == owner)
        stmt = stmt.order_by(CalendarEvent.start_time)
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "owner": r.owner,
                "date": str(r.event_date),
                "start": r.start_time,
                "end": r.end_time,
                "title": r.title,
                "location": r.location,
                "attendees": r.attendees,
                "note": r.note,
            }
            for r in rows
        ]
