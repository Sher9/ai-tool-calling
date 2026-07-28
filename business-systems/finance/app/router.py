"""财务 ERP REST 接口（仿真业务系统的「调用入口」）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app import service as svc
from app.auth import Actor, get_actor

router = APIRouter(dependencies=[Depends(get_actor)])


@router.get("/invoice")
async def invoices(
    supplier: str = Query("", description="供应商关键字"),
    actor: Actor = Depends(get_actor),
):
    return {"items": await svc.finance_invoices(actor, supplier)}


@router.get("/revenue")
async def revenue(
    month: str = Query("", description="月份，如 2026-07"),
    actor: Actor = Depends(get_actor),
):
    return {"items": await svc.finance_revenue(actor, month)}


@router.get("/expense")
async def expenses(
    category: str = Query("", description="报销类别，如 差旅"),
    actor: Actor = Depends(get_actor),
):
    return {"items": await svc.finance_expenses(actor, category)}


@router.get("/summary")
async def summary(actor: Actor = Depends(get_actor)):
    s = await svc.finance_summary(actor)
    if s is None:
        from fastapi import HTTPException, status as http_status

        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="无权限访问财务数据")
    return {"item": s}
