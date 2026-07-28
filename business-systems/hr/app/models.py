"""HR 库表：员工 / 考勤 / 假期。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HrEmployee(Base):
    __tablename__ = "hr_employees"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_no: Mapped[str] = mapped_column(String(32), unique=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)  # 关联平台账号
    name: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(64), default="")
    position: Mapped[str] = mapped_column(String(64), default="")
    manager: Mapped[str] = mapped_column(String(64), default="")  # 直属上级(平台用户名)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="在职")  # 在职/离职
    leave_balance: Mapped[int] = mapped_column(Integer, default=0)  # 剩余年假(天)
    id_card: Mapped[str] = mapped_column(String(32), default="")  # 敏感
    salary: Mapped[float] = mapped_column(Numeric(12, 2), default=0)  # 敏感
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class HrAttendance(Base):
    __tablename__ = "hr_attendance"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("hr_employees.id", ondelete="CASCADE"))
    work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    check_in: Mapped[str] = mapped_column(String(8), default="")
    check_out: Mapped[str] = mapped_column(String(8), default="")
    status: Mapped[str] = mapped_column(String(16), default="正常")  # 正常/迟到/缺勤/请假


class HrLeave(Base):
    __tablename__ = "hr_leaves"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("hr_employees.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(32), default="年假")  # 年假/事假/病假
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="审批中")  # 审批中/已通过/已驳回
    approver: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
