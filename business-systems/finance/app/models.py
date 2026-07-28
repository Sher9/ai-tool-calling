"""财务 ERP 库表：发票 / 营收 / 报销。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FinInvoice(Base):
    __tablename__ = "fin_invoices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    invoice_no: Mapped[str] = mapped_column(String(64), unique=True)
    supplier: Mapped[str] = mapped_column(String(128), default="")
    buyer: Mapped[str] = mapped_column(String(128), default="")
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    tax_no: Mapped[str] = mapped_column(String(32), default="")  # 敏感
    bank_account: Mapped[str] = mapped_column(String(32), default="")  # 敏感
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="待付款")  # 待付款/已付款


class FinRevenue(Base):
    __tablename__ = "fin_revenue"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    month: Mapped[str] = mapped_column(String(16), default="")  # 2026-07
    revenue: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    profit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    note: Mapped[str] = mapped_column(Text, default="")


class FinExpense(Base):
    __tablename__ = "fin_expenses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), default="")  # 差旅/办公/采购/招待
    applicant: Mapped[str] = mapped_column(String(64), default="")
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    occur_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="待报销")  # 待报销/已报销
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
