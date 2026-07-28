"""HR REST 接口（仿真业务系统的「调用入口」）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app import service as svc
from app.auth import Actor, get_actor

router = APIRouter(dependencies=[Depends(get_actor)])


class LeaveApply(BaseModel):
    type: str = "年假"
    start_date: str = ""
    end_date: str = ""
    days: int = 0
    reason: str = ""


@router.get("/employees/me")
async def employee_me(
    username: str = Query("", description="查询指定账号(仅 HR/管理员)；留空查自己"),
    actor: Actor = Depends(get_actor),
):
    rec = await svc.hr_get_employee(actor, username)
    if not rec:
        return {"item": None, "message": "未查询到员工档案或无查看权限"}
    return {"item": rec}


@router.get("/employees/{eid}")
async def employee_by_id(eid: str, actor: Actor = Depends(get_actor)):
    # 允许按 id 查询（权限复用 get_employee 的归属逻辑）
    async with svc.async_session_maker() as s:
        from app.models import HrEmployee

        e = await s.get(HrEmployee, eid)
        if not e:
            return {"item": None, "message": "未查询到员工档案"}
    rec = await svc.hr_get_employee(actor, e.username)
    if not rec:
        return {"item": None, "message": "无查看权限"}
    return {"item": rec}


@router.get("/attendance")
async def attendance(
    month: str = Query("", description="月份，如 2026-07"),
    username: str = Query("", description="查询指定账号(仅 HR/管理员)；留空查自己"),
    actor: Actor = Depends(get_actor),
):
    return {"items": await svc.hr_attendance(actor, username, month)}


@router.get("/leaves")
async def leaves(
    username: str = Query("", description="查询指定账号(仅 HR/管理员)；留空查自己"),
    actor: Actor = Depends(get_actor),
):
    return {"items": await svc.hr_leaves(actor, username)}


@router.post("/leaves")
async def apply_leave(payload: LeaveApply, actor: Actor = Depends(get_actor)):
    try:
        rec = await svc.hr_leave_apply(actor, payload.model_dump())
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e))
    return {"item": rec}
