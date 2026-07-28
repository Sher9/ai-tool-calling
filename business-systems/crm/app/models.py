"""CRM 库表：客户 / 商机。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CrmCustomer(Base):
    __tablename__ = "crm_customers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    industry: Mapped[str] = mapped_column(String(64), default="")
    stage: Mapped[str] = mapped_column(String(32), default="线索")  # 线索/商机/谈判/成交/流失
    owner: Mapped[str] = mapped_column(String(64), default="")  # 负责人(平台用户名)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    contact_name: Mapped[str] = mapped_column(String(64), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    contact_email: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CrmDeal(Base):
    __tablename__ = "crm_deals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("crm_customers.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(128), default="")
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    stage: Mapped[str] = mapped_column(String(32), default="商机")
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
