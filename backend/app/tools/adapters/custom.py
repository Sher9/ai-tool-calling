"""自定义内部业务工具：库存 / 产品参数 / 资源申请 / 报价单.

真实接入方式（默认已指向 business-systems/biz 仿真服务）：
  - 配置 BIZ_BASE_URL（容器内 http://biz:8085，本机 http://localhost:8085）
  - 配置 BIZ_TOKEN（与各业务微服务 SERVICE_TOKEN 一致，默认 biz-svc-2026-token）
  - 并将 MOCK_TOOLS=false，即真实调用，不再返回仿真数据。
未配置且 MOCK_TOOLS=false 时该工具会明确报错（不再静默返回假数据）。
"""
from __future__ import annotations

import json

from app.config import settings
from app.core.http import aget, apost
from app.tools.base import ToolContext, ToolResult, fail, ok_table, ok_text

# biz 服务各接口路径
_INVENTORY_SEARCH = "/inventory/search"
_PRODUCT = "/product"
_PRODUCT_LIST = "/product/list"
_QUOTE = "/quote/generate"


def _actor_headers(ctx: ToolContext) -> dict:
    return {"X-Act-User": ctx.username or "", "X-Act-Role": ctx.role or "employee"}


def _rows_from(data) -> list[list]:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        cols = list(data[0].keys())
        return [cols, *[[r.get(c) for c in cols] for r in data]]
    return []


async def inventory_query(args: dict, ctx: ToolContext) -> ToolResult:
    keyword = args.get("keyword", "")
    if settings.MOCK_TOOLS or not settings.BIZ_BASE_URL:
        if keyword == "无":
            return ok_text("库存系统中未找到匹配商品。")
        # keyword 为空视为查询全部库存；否则按关键字过滤
        if not keyword:
            rows = [["SKU", "名称", "库存", "仓库", "单价"],
                    ["SKU-A01", "主机 X1", 120, "华东仓", 9800],
                    ["SKU-B02", "交换机 S100", 86, "华东仓", 2200],
                    ["SKU-C03", "主机 X2 Pro", 34, "华南仓", 12600],
                    ["SKU-D04", "光模块 10G", 540, "华北仓", 180]]
        else:
            rows = [["SKU", "名称", "库存", "仓库", "单价"],
                    ["SKU-A01", f"{keyword} X1", 120, "华东仓", 9800]]
        return ok_table(rows[0], rows[1:])
    try:
        base = settings.BIZ_BASE_URL.rstrip("/")
        data = await aget(base + _INVENTORY_SEARCH, token=settings.BIZ_TOKEN,
                          params={"keyword": keyword}, headers=_actor_headers(ctx))
        items = (data.get("items") if isinstance(data, dict) else data) or []
        rows = _rows_from(items) or [["SKU", "名称", "库存", "仓库", "单价"]]
        return ok_table(rows[0], rows[1:]) if len(rows) > 1 else ok_text("库存系统中未找到匹配商品。")
    except Exception as e:  # noqa: BLE001
        return fail(f"库存查询失败：{e}")


async def product_param(args: dict, ctx: ToolContext) -> ToolResult:
    model = args.get("model", "").strip()
    if settings.MOCK_TOOLS or not settings.BIZ_BASE_URL:
        if not model:
            # 未指定型号 → 返回全部产品列表
            rows = [["型号", "名称", "CPU", "内存", "单价", "质保"],
                    ["S100", "交换机 S100", "—", "—", 2200, "3年"],
                    ["X1", "主机 X1", "16C", "32G", 9800, "3年"],
                    ["X2 Pro", "主机 X2 Pro", "32C", "64G", 12600, "5年"]]
            return ok_table(rows[0], rows[1:])
        return ok_text(f"【产品参数】\n- model: {model}\n- cpu: 16C/32G\n- price: 9800\n- warranty: 3年")
    if not model:
        # 真实模式：未指定型号 → 查询全部产品列表
        try:
            base = settings.BIZ_BASE_URL.rstrip("/")
            data = await aget(base + _PRODUCT_LIST, token=settings.BIZ_TOKEN,
                              headers=_actor_headers(ctx))
            items = (data.get("items") if isinstance(data, dict) else data) or []
            rows = _rows_from(items)
            if len(rows) < 2:
                return ok_text("产品库中暂无产品。")
            return ok_table(rows[0], rows[1:])
        except Exception as e:  # noqa: BLE001
            return fail(f"产品列表查询失败：{e}")
    try:
        base = settings.BIZ_BASE_URL.rstrip("/")
        data = await aget(base + f"{_PRODUCT}/{model}", token=settings.BIZ_TOKEN,
                          headers=_actor_headers(ctx))
        item = data.get("item") if isinstance(data, dict) else None
        if not item:
            return ok_text(f"未找到型号为 {model} 的产品参数。")
        lines = "\n".join(f"- {k}: {v}" for k, v in item.items())
        return ok_text(f"【产品参数】\n{lines}")
    except Exception as e:  # noqa: BLE001
        return fail(f"产品参数查询失败：{e}")


async def quote_generate(args: dict, ctx: ToolContext) -> ToolResult:
    items = args.get("items", []) or []
    customer = args.get("customer", "")
    if settings.MOCK_TOOLS or not settings.BIZ_BASE_URL:
        if not items:
            items = [{"name": "主机 X1", "qty": 2, "price": 9800}]
        total = sum(i.get("qty", 1) * i.get("price", 0) for i in items)
        lines = "\n".join(f"- {i.get('name')} x{i.get('qty', 1)} @ {i.get('price', 0)}" for i in items)
        return ok_text(f"【客户报价单】\n{lines}\n合计：{total} 元\n（联系人：{ctx.username}）")
    if not items:
        return ok_text("报价单缺少明细（items）。未从你的描述中解析出任何产品与数量。")
    try:
        base = settings.BIZ_BASE_URL.rstrip("/")
        # 逐条补全单价：biz 的报价单不会自行查价，需先按型号查产品目录拿到 price
        for it in items:
            if not it.get("price"):
                model = it.get("model") or it.get("name")
                try:
                    pdata = await aget(base + f"{_PRODUCT}/{model}", token=settings.BIZ_TOKEN,
                                       headers=_actor_headers(ctx))
                    if isinstance(pdata, dict) and pdata.get("item"):
                        it["price"] = float(pdata["item"].get("price", 0) or 0)
                except Exception:  # noqa: BLE001
                    it["price"] = 0
        payload_items = [
            {"name": it.get("name", ""), "qty": int(it.get("qty", 1)), "price": float(it.get("price", 0))}
            for it in items
        ]
        data = await apost(base + _QUOTE, token=settings.BIZ_TOKEN,
                           json={"items": payload_items, "customer": customer},
                           headers=_actor_headers(ctx))
        lines = "\n".join(
            f"- {i.get('name')} x{i.get('qty', 1)} @ {i.get('price', 0)} = {i.get('subtotal', 0)}"
            for i in data.get("items", [])
        )
        return ok_text(f"【客户报价单】\n单号：{data.get('quote_id')}\n{lines}\n合计：{data.get('total')} 元")
    except Exception as e:  # noqa: BLE001
        return fail(f"报价单生成失败：{e}")


ADAPTERS = {
    "inventory_query": inventory_query,
    "product_param": product_param,
    "quote_generate": quote_generate,
}
