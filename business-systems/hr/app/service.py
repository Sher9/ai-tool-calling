"""HR 业务逻辑：真实 DB 操作 + 行级权限（本人或人事/管理员可见，敏感字段仅 HR/管理员）。"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import select

from app.auth import Actor
from app.db import async_session_maker
from app.models import HrAttendance, HrEmployee, HrLeave

SENSITIVE_ROLES = {"admin", "hr"}


def _emp(e: HrEmployee, sensitive: bool) -> dict:
    d = {
        "id": e.id,
        "employee_no": e.employee_no,
        "username": e.username,
        "name": e.name,
        "department": e.department,
        "position": e.position,
        "manager": e.manager,
        "hire_date": str(e.hire_date) if e.hire_date else "",
        "status": e.status,
        "leave_balance": e.leave_balance,
    }
    if sensitive:
        d.update(id_card=e.id_card, salary=float(e.salary))
    return d


async def hr_get_employee(actor: Actor, username: str) -> Optional[dict]:
    target = username or actor.username
    async with async_session_maker() as s:
        e = (await s.execute(select(HrEmployee).where(HrEmployee.username == target))).scalar_one_or_none()
        if not e:
            return None
        # 仅本人或人事/管理员可见
        if target != actor.username and actor.role not in SENSITIVE_ROLES:
            return None
        return _emp(e, sensitive=actor.role in SENSITIVE_ROLES)


async def hr_attendance(actor: Actor, username: str, month: str) -> list[dict]:
    target = username or actor.username
    if target != actor.username and actor.role not in SENSITIVE_ROLES:
        return []
    async with async_session_maker() as s:
        e = (await s.execute(select(HrEmployee).where(HrEmployee.username == target))).scalar_one_or_none()
        if not e:
            return []
        stmt = select(HrAttendance).where(HrAttendance.employee_id == e.id)
        if month:
            stmt = stmt.where(HrAttendance.work_date.cast(String).like(f"{month}%"))
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "work_date": str(a.work_date) if a.work_date else "",
                "check_in": a.check_in,
                "check_out": a.check_out,
                "status": a.status,
            }
            for a in rows
        ]


async def hr_leaves(actor: Actor, username: str) -> list[dict]:
    target = username or actor.username
    async with async_session_maker() as s:
        e = (await s.execute(select(HrEmployee).where(HrEmployee.username == target))).scalar_one_or_none()
        if not e:
            return []
        # 普通员工只能看自己；HR/管理员可查看指定人的全部请假
        if actor.role not in SENSITIVE_ROLES and target != actor.username:
            return []
        rows = (await s.execute(
            select(HrLeave).where(HrLeave.employee_id == e.id)
        )).scalars().all()
        return [
            {
                "id": l.id,
                "type": l.type,
                "start_date": str(l.start_date) if l.start_date else "",
                "end_date": str(l.end_date) if l.end_date else "",
                "days": l.days,
                "reason": l.reason,
                "status": l.status,
                "approver": l.approver,
            }
            for l in rows
        ]


async def hr_leave_apply(actor: Actor, payload: dict) -> dict:
    async with async_session_maker() as s:
        e = (await s.execute(
            select(HrEmployee).where(HrEmployee.username == actor.username)
        )).scalar_one_or_none()
        if not e:
            raise ValueError("未找到当前操作人的员工档案")
        lid = payload.get("id") or f"lv-{actor.username}-{int(time.time())}"
        leave = HrLeave(
            id=lid,
            employee_id=e.id,
            type=payload.get("type", "年假"),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            days=int(payload.get("days", 0) or 0),
            reason=payload.get("reason", ""),
            status="审批中",
        )
        s.add(leave)
        await s.commit()
        return {
            "id": lid,
            "employee": e.username,
            "type": leave.type,
            "status": leave.status,
        }
