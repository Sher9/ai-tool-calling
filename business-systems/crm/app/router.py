"""CRM REST 接口（仿真业务系统的「调用入口」）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app import service as svc
from app.auth import Actor, get_actor

router = APIRouter(dependencies=[Depends(get_actor)])


@router.get("/customers")
async def list_customers(
    keyword: str = Query("", description="客户名称关键字"),
    actor: Actor = Depends(get_actor),
):
    res = await svc.crm_search(keyword, actor)
    return {"items": res["items"], "total": len(res["items"]), "message": res.get("message")}


@router.get("/customers/{cid}")
async def get_customer(cid: str, actor: Actor = Depends(get_actor)):
    rec = await svc.crm_customer(cid, actor)
    if not rec:
        return {"item": None, "message": "未找到该客户或无查看权限"}
    return {"item": rec}


@router.get("/deals")
async def list_deals(actor: Actor = Depends(get_actor)):
    items = await svc.crm_deals(actor)
    return {"items": items, "total": len(items)}


@router.get("/stats")
async def stats(actor: Actor = Depends(get_actor)):
    return {"items": await svc.crm_stats(actor)}
