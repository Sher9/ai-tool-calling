"""OA 业务逻辑：真实 DB 操作 + 审批流推进 + 权限（申请人/审批人/管理员可见）。"""
from __future__ import annotations

import datetime
import time
from typing import Optional

from sqlalchemy import select

from app.auth import Actor
from app.db import async_session_maker
from app.models import OaApproval, OaApprovalNode

# 各类审批的节点链（审批节点名 -> 默认审批人）
# 部门主管统一为 admin，财务为 dave，人事为 erin，总经理为 admin（仿真组织）
NODE_CHAINS = {
    "请假": [("部门主管", "admin"), ("人事", "erin")],
    "出差": [("部门主管", "admin"), ("财务", "dave")],
    "报销": [("部门主管", "admin"), ("财务", "dave")],
    "采购": [("部门主管", "admin"), ("财务", "dave"), ("总经理", "admin")],
}
DEFAULT_CHAIN = [("部门主管", "admin"), ("财务", "dave")]


def _nodes_info(approval: OaApproval) -> list[dict]:
    return [
        {
            "node_name": n.node_name,
            "approver": n.approver,
            "status": n.status,
            "acted_at": str(n.acted_at) if n.acted_at else "",
            "comment": n.comment,
        }
        for n in sorted(approval.nodes, key=lambda x: x.seq)
    ]


def _approval_dict(a: OaApproval) -> dict:
    return {
        "id": a.id,
        "type": a.type,
        "applicant": a.applicant,
        "title": a.title,
        "content": a.content,
        "status": a.status,
        "current_node": a.current_node,
        "created_at": str(a.created_at),
        "nodes": _nodes_info(a),
    }


async def oa_create(
    flow_type: str, applicant: str, title: str, content: str, actor: Actor
) -> dict:
    chain = NODE_CHAINS.get(flow_type, DEFAULT_CHAIN)
    ap_id = f"oa-{int(time.time())}"
    async with async_session_maker() as s:
        ap = OaApproval(
            id=ap_id,
            type=flow_type,
            applicant=applicant or actor.username,
            title=title,
            content=content,
            status="审批中",
            current_node=chain[0][0],
        )
        s.add(ap)
        for i, (node_name, approver) in enumerate(chain):
            s.add(
                OaApprovalNode(
                    id=f"{ap_id}-n{i+1}",
                    approval_id=ap_id,
                    node_name=node_name,
                    seq=i + 1,
                    approver=approver,
                    status="待审批",
                )
            )
        await s.commit()
        # 重新加载节点
        fresh = (await s.execute(
            select(OaApproval).where(OaApproval.id == ap_id)
        )).scalar_one()
        return _approval_dict(fresh)


async def oa_get(ap_id: str) -> Optional[dict]:
    async with async_session_maker() as s:
        a = (await s.execute(
            select(OaApproval).where(OaApproval.id == ap_id)
        )).scalar_one_or_none()
        if not a:
            return None
        return _approval_dict(a)


async def oa_list(actor: Actor, status: str) -> list[dict]:
    async with async_session_maker() as s:
        stmt = select(OaApproval)
        if status:
            stmt = stmt.where(OaApproval.status == status)
        rows = (await s.execute(stmt)).scalars().all()
        result = []
        for a in rows:
            # 申请人本人 / 管理员 / 当前节点审批人 可见
            is_approver = any(
                n.status == "待审批" and n.approver == actor.username
                for n in a.nodes
            )
            if (
                a.applicant == actor.username
                or actor.role == "admin"
                or is_approver
            ):
                result.append(_approval_dict(a))
        return result


async def oa_approve(ap_id: str, action: str, actor: Actor) -> dict:
    async with async_session_maker() as s:
        a = (await s.execute(
            select(OaApproval).where(OaApproval.id == ap_id)
        )).scalar_one_or_none()
        if not a:
            raise ValueError("审批单不存在")
        if a.status != "审批中":
            raise ValueError("该审批单已结束，无法操作")
        # 找到当前待审批节点（seq 最小且待审批）
        pending = sorted(
            [n for n in a.nodes if n.status == "待审批"], key=lambda x: x.seq
        )
        if not pending:
            raise ValueError("无待审批节点")
        node = pending[0]
        if actor.role != "admin" and node.approver != actor.username:
            raise ValueError(f"当前节点「{node.node_name}」仅限 {node.approver} 审批")
        node.status = "已通过" if action == "approve" else "已驳回"
        node.acted_at = datetime.datetime.now()
        if node.status == "已驳回":
            a.status = "已驳回"
            a.current_node = ""
        else:
            nxt = sorted(
                [n for n in a.nodes if n.status == "待审批"], key=lambda x: x.seq
            )
            if not nxt:
                a.status = "已通过"
                a.current_node = ""
            else:
                a.current_node = nxt[0].node_name
        await s.commit()
        fresh = (await s.execute(
            select(OaApproval).where(OaApproval.id == ap_id)
        )).scalar_one()
        return _approval_dict(fresh)
