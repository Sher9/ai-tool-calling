"""OA 演示数据（幂等写入）。"""
from __future__ import annotations

from sqlalchemy import select

from app.db import async_session_maker
from app.models import OaApproval, OaApprovalNode

SEED = [
    dict(
        id="oa-seed-001", type="请假", applicant="bob", title="Bob 年假申请",
        content="申请 8/1-8/3 年假 3 天", status="审批中", current_node="部门主管",
        nodes=[("部门主管", "admin", "待审批"), ("人事", "erin", "待审批")],
    ),
    dict(
        id="oa-seed-002", type="报销", applicant="carol", title="Carol 设备采购报销",
        content="研发设备报销 12500 元", status="已通过", current_node="",
        nodes=[("部门主管", "admin", "已通过"), ("财务", "dave", "已通过")],
    ),
]


async def seed(session) -> None:
    for a in SEED:
        if await session.get(OaApproval, a["id"]):
            continue
        ap = OaApproval(
            id=a["id"], type=a["type"], applicant=a["applicant"], title=a["title"],
            content=a["content"], status=a["status"], current_node=a["current_node"],
        )
        session.add(ap)
        for i, (node_name, approver, nstatus) in enumerate(a["nodes"]):
            session.add(
                OaApprovalNode(
                    id=f"{a['id']}-n{i+1}", approval_id=a["id"], node_name=node_name,
                    seq=i + 1, approver=approver, status=nstatus,
                )
            )
    await session.commit()
