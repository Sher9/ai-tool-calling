"""CRM 演示数据（幂等写入）。"""
from __future__ import annotations

from app.db import async_session_maker
from app.models import CrmCustomer, CrmDeal

# owner 对齐真实登录账号：
#   - sql/seed_users.sql 的销售账号为 ivan；backend/app/seed.py 的销售账号为 alice/bob
# 因此把演示客户分配给 ivan / alice / bob，使“查一下我的客户”对这几个账号都能返回数据。
CUSTOMERS = [
    dict(id="cust-001", name="张三", industry="互联网", stage="成交", owner="ivan",
         amount=1200000, contact_name="王总", contact_phone="13800001111",
         contact_email="wang@yuntu.com", remark="年度框架合同"),
    dict(id="cust-002", name="李四", industry="制造业", stage="谈判", owner="ivan",
         amount=860000, contact_name="李经理", contact_phone="13900002222",
         contact_email="li@hengsheng.com", remark="待法务评审"),
    dict(id="cust-003", name="王五", industry="物流", stage="商机", owner="alice",
         amount=540000, contact_name="赵主管", contact_phone="13700003333",
         contact_email="zhao@ruichi.com", remark="初步接洽"),
    dict(id="cust-004", name="赵六", industry="传媒", stage="线索", owner="bob",
         amount=230000, contact_name="陈女士", contact_phone="13600004444",
         contact_email="chen@xinghe.com", remark="官网留资"),
]

DEALS = [
    dict(id="deal-001", customer_id="cust-001", title="云图科技-一期采购", amount=1200000,
         stage="成交", expected_close_date="2026-05-30", owner="ivan"),
    dict(id="deal-002", customer_id="cust-002", title="恒昇制造-设备升级", amount=860000,
         stage="谈判", expected_close_date="2026-08-15", owner="ivan"),
    dict(id="deal-003", customer_id="cust-003", title="锐驰物流-系统对接", amount=540000,
         stage="商机", expected_close_date="2026-09-01", owner="alice"),
]


async def seed(session) -> None:
    """幂等写入；若记录已存在则更新其字段（含 owner），便于修正历史数据的 owner 不匹配。"""
    for c in CUSTOMERS:
        existing = await session.get(CrmCustomer, c["id"])
        if existing:
            for k, v in c.items():
                if k != "id":
                    setattr(existing, k, v)
        else:
            session.add(CrmCustomer(**c))
    for d in DEALS:
        existing = await session.get(CrmDeal, d["id"])
        if existing:
            for k, v in d.items():
                if k != "id":
                    setattr(existing, k, v)
        else:
            session.add(CrmDeal(**d))
    await session.commit()
