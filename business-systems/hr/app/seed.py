"""HR 演示数据（幂等写入）。"""
from __future__ import annotations

from app.db import async_session_maker
from app.models import HrAttendance, HrEmployee, HrLeave

EMPLOYEES = [
    dict(id="emp-001", employee_no="E0001", username="admin", name="管理员", department="总经办",
         position="平台管理员", manager="", hire_date="2023-01-01", status="在职", leave_balance=15,
         id_card="110101199001011234", salary=40000),
    dict(id="emp-002", employee_no="E0002", username="alice", name="Alice", department="销售部",
         position="销售经理", manager="admin", hire_date="2023-03-15", status="在职", leave_balance=10,
         id_card="310101199205062345", salary=22000),
    dict(id="emp-003", employee_no="E0003", username="bob", name="Bob", department="销售部",
         position="销售代表", manager="alice", hire_date="2023-06-01", status="在职", leave_balance=8,
         id_card="440101199308153456", salary=15000),
    dict(id="emp-004", employee_no="E0004", username="carol", name="Carol", department="研发部",
         position="研发主管", manager="admin", hire_date="2022-09-01", status="在职", leave_balance=12,
         id_card="510101199010204567", salary=28000),
    dict(id="emp-005", employee_no="E0005", username="dave", name="Dave", department="财务部",
         position="财务专员", manager="admin", hire_date="2022-11-01", status="在职", leave_balance=9,
         id_card="320101199112055678", salary=18000),
    dict(id="emp-006", employee_no="E0006", username="erin", name="Erin", department="人事部",
         position="人事专员", manager="admin", hire_date="2023-02-01", status="在职", leave_balance=11,
         id_card="120101199203106789", salary=16000),
]

ATTENDANCE = [
    dict(id="att-001", employee_id="emp-001", work_date="2026-07-01", check_in="09:01", check_out="18:30", status="正常"),
    dict(id="att-002", employee_id="emp-001", work_date="2026-07-02", check_in="09:02", check_out="18:30", status="正常"),
    dict(id="att-003", employee_id="emp-001", work_date="2026-07-03", check_in="09:00", check_out="18:30", status="正常"),
    dict(id="att-004", employee_id="emp-002", work_date="2026-07-01", check_in="09:05", check_out="18:30", status="正常"),
    dict(id="att-005", employee_id="emp-002", work_date="2026-07-02", check_in="09:03", check_out="18:30", status="正常"),
    dict(id="att-006", employee_id="emp-003", work_date="2026-07-01", check_in="09:20", check_out="18:30", status="迟到"),
]

LEAVES = [
    dict(id="lv-001", employee_id="emp-003", type="年假", start_date="2026-08-01", end_date="2026-08-03",
         days=3, reason="回家探亲", status="已通过", approver="alice"),
    dict(id="lv-002", employee_id="emp-002", type="事假", start_date="2026-07-25", end_date="2026-07-25",
         days=1, reason="病假", status="审批中", approver=""),
]


async def seed(session) -> None:
    for e in EMPLOYEES:
        if not await session.get(HrEmployee, e["id"]):
            session.add(HrEmployee(**e))
    for a in ATTENDANCE:
        if not await session.get(HrAttendance, a["id"]):
            session.add(HrAttendance(**a))
    for l in LEAVES:
        if not await session.get(HrLeave, l["id"]):
            session.add(HrLeave(**l))
    await session.commit()
