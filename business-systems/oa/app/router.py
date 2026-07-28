"""OA REST 接口（仿真业务系统的「调用入口」）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel

from app import service as svc
from app.auth import Actor, get_actor

router = APIRouter(dependencies=[Depends(get_actor)])


class ApplyIn(BaseModel):
    type: str  # 请假/出差/报销/采购
    applicant: str = ""
    title: str = ""
    content: str = ""


class ApproveIn(BaseModel):
    action: str  # approve / reject


@router.post("/apply")
async def apply(payload: ApplyIn, actor: Actor = Depends(get_actor)):
    rec = await svc.oa_create(
        payload.type, payload.applicant, payload.title, payload.content, actor
    )
    return {"item": rec}


@router.get("/approvals")
async def list_approvals(
    status: str = Query("", description="按状态过滤：审批中/已通过/已驳回"),
    actor: Actor = Depends(get_actor),
):
    return {"items": await svc.oa_list(actor, status)}


@router.get("/approvals/{ap_id}")
async def get_approval(ap_id: str, actor: Actor = Depends(get_actor)):
    rec = await svc.oa_get(ap_id)
    if not rec:
        return {"item": None, "message": "审批单不存在"}
    # 简单可见性校验：申请人/审批人/管理员
    is_approver = any(n["status"] == "待审批" and n["approver"] == actor.username for n in rec["nodes"])
    if not (rec["applicant"] == actor.username or actor.role == "admin" or is_approver):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="无权限查看该审批单")
    return {"item": rec}


@router.post("/approvals/{ap_id}/approve")
async def approve(ap_id: str, payload: ApproveIn, actor: Actor = Depends(get_actor)):
    try:
        rec = await svc.oa_approve(ap_id, payload.action, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": rec}
