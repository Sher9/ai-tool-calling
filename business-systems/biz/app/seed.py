"""BIZ 演示数据（幂等写入）。"""
from __future__ import annotations

from app.db import async_session_maker
from app.models import CalendarEvent, InventoryItem, ProductParam

INVENTORY = [
    dict(sku="SKU-A01", name="主机 X1", category="服务器", stock=120, warehouse="华东仓", price=9800),
    dict(sku="SKU-A02", name="主机 X2 Pro", category="服务器", stock=64, warehouse="华东仓", price=15800),
    dict(sku="SKU-B01", name="交换机 S100", category="网络设备", stock=300, warehouse="华北仓", price=2200),
    dict(sku="SKU-B02", name="光纤模块 10G", category="网络设备", stock=1500, warehouse="华北仓", price=180),
    dict(sku="SKU-C01", name="工控一体机 T7", category="终端", stock=88, warehouse="华南仓", price=4600),
]

PRODUCTS = [
    dict(model="X1", name="主机 X1", cpu="16C/32G", memory="32G", disk="1T SSD",
         price=9800, warranty="3年", remark="标准机架式服务器"),
    dict(model="X2 Pro", name="主机 X2 Pro", cpu="32C/64G", memory="64G", disk="2T NVMe",
         price=15800, warranty="3年", remark="高性能计算节点"),
    dict(model="S100", name="交换机 S100", cpu="-", memory="-", disk="-",
         price=2200, warranty="1年", remark="48口万兆接入交换机"),
]

from datetime import date, timedelta

_today = date.today()
CALENDAR = [
    dict(id="cal-001", owner="alice", event_date=_today, start_time="10:00", end_time="11:00",
         title="部门周会", location="3F-会议室A", attendees="alice,bob,carol", note="同步本周目标与风险"),
    dict(id="cal-002", owner="alice", event_date=_today, start_time="14:30", end_time="15:30",
         title="客户演示", location="线上-腾讯会议", attendees="alice,david", note="产品方案演示"),
    dict(id="cal-003", owner="admin", event_date=_today, start_time="17:00", end_time="18:00",
         title="版本发布评审", location="3F-会议室B", attendees="bob,carol", note="V2.3 发布前评审"),
    dict(id="cal-004", owner="bob", event_date=_today, start_time="09:30", end_time="10:00",
         title="晨会站会", location="线上", attendees="bob,team", note="每日站会"),
]


async def seed(session) -> None:
    for r in INVENTORY:
        if not await session.get(InventoryItem, r["sku"]):
            session.add(InventoryItem(**r))
    for p in PRODUCTS:
        if not await session.get(ProductParam, p["model"]):
            session.add(ProductParam(**p))
    for c in CALENDAR:
        if not await session.get(CalendarEvent, c["id"]):
            session.add(CalendarEvent(**c))
    await session.commit()
