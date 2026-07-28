"""BIZ REST 接口（仿真业务系统的「调用入口」）。"""
from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app import service as svc
from app.auth import Actor, get_actor

router = APIRouter(dependencies=[Depends(get_actor)])


# ---- 库存查询 ----
@router.get("/inventory/search")
async def inventory_search(
    keyword: str = Query("", description="商品名称关键字"),
    actor: Actor = Depends(get_actor),
):
    items = await svc.inventory_search(keyword, actor)
    return {"items": items, "total": len(items)}


# ---- 产品参数 ----
@router.get("/product/{model}")
async def product_param(model: str, actor: Actor = Depends(get_actor)):
    rec = await svc.product_param(model, actor)
    if not rec:
        return {"item": None, "message": "未找到该型号产品或无查看权限"}
    return {"item": rec}


# ---- 报价单生成 ----
class QuoteItemIn(BaseModel):
    name: str
    qty: int = 1
    price: float = 0


class QuoteGenIn(BaseModel):
    items: list[QuoteItemIn]
    customer: str = ""


@router.post("/quote/generate")
async def quote_generate(body: QuoteGenIn, actor: Actor = Depends(get_actor)):
    items = [it.model_dump() for it in body.items]
    return await svc.quote_generate(items, actor.username, body.customer, actor)


# ---- 日历日程查询 ----
@router.get("/calendar/events")
async def calendar_events(
    date: str = Query("", description="日程日期 YYYY-MM-DD，默认今日"),
    actor: Actor = Depends(get_actor),
):
    from datetime import date as date_type

    target = date_type.today()
    if date:
        try:
            target = date_type.fromisoformat(date)
        except ValueError:
            pass
    events = await svc.calendar_events(target, actor.username)
    return {"date": str(target), "owner": actor.username,
            "events": events, "total": len(events)}
