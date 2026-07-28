"""BIZ 库表：库存 / 产品参数 / 资源申请 / 报价单。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="")
    stock: Mapped[int] = mapped_column(default=0)
    warehouse: Mapped[str] = mapped_column(String(64), default="")
    price: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProductParam(Base):
    __tablename__ = "product_params"

    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cpu: Mapped[str] = mapped_column(String(64), default="")
    memory: Mapped[str] = mapped_column(String(64), default="")
    disk: Mapped[str] = mapped_column(String(64), default="")
    price: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    warranty: Mapped[str] = mapped_column(String(32), default="")
    remark: Mapped[str] = mapped_column(Text, default="")


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), default="anonymous")
    customer: Mapped[str] = mapped_column(String(128), default="")
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quote_id: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(128), default="")
    qty: Mapped[int] = mapped_column(default=1)
    price: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), default="anonymous")  # 归属人（与日程系统账号对应）
    event_date: Mapped[date] = mapped_column(Date, default=date.today)    # 日程日期
    start_time: Mapped[str] = mapped_column(String(16), default="09:00")  # 开始时间 HH:MM
    end_time: Mapped[str] = mapped_column(String(16), default="10:00")    # 结束时间 HH:MM
    title: Mapped[str] = mapped_column(String(128), default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    attendees: Mapped[str] = mapped_column(String(256), default="")       # 逗号分隔的参与人
    note: Mapped[str] = mapped_column(Text, default="")
