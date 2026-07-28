"""业务系统工具（分部门隔离权限）: CRM / HR / 财务ERP / OA 审批.

调用优先级：
  1) 配置了外部系统地址（CRM_BASE_URL 等，默认指向 business-systems/ 的 Spring Cloud Gateway
     网关，端口 8080，路径前缀 /crm /hr /finance /oa）-> 走 HTTP 调用真实外部业务系统；
  2) 开启了 MOCK_TOOLS -> 返回本地静态演示数据（无需数据库）；
  3) 未配置且未开启 MOCK -> 明确报错。

四个「仿真业务系统」已是独立项目（不同端口），与 Agent 平台解耦。调用时携带共享服务令牌
（Authorization: Bearer <token>）并通过 X-Act-User / X-Act-Role 头透传操作人身份，
供各业务系统做行级权限判断（模拟网关透传身份的内部微服务）。
"""
from __future__ import annotations

import json

from app.config import settings
from app.core.http import aget, apost
from app.core.masking import mask_text
from app.tools.base import ToolContext, ToolResult, fail, ok_table, ok_text


def _fmt(data) -> str:
    """将真实返回格式化为文本，并对敏感字段统一脱敏。"""
    text = json.dumps(data, ensure_ascii=False, indent=2) if not isinstance(data, str) else data
    return mask_text(text)


def _actor_headers(ctx: ToolContext) -> dict[str, str]:
    """透传操作人身份给业务系统（模拟网关注入）。"""
    return {"X-Act-User": ctx.username or "anonymous", "X-Act-Role": ctx.role or "employee"}


def _unwrap(data):
    """业务系统统一返回 {"item": ...} / {"items": ...}，取出可渲染主体。"""
    if isinstance(data, dict):
        if "item" in data:
            return data["item"]
        if "items" in data:
            return data["items"]
    return data


# ============================================================
# CRM
# ============================================================
async def crm_query(args: dict, ctx: ToolContext) -> ToolResult:
    keyword = str(args.get("keyword") or "").strip()
    if settings.CRM_BASE_URL:
        try:
            data = await aget(
                settings.CRM_BASE_URL.rstrip("/") + "/customers",
                token=settings.CRM_TOKEN,
                params={"keyword": keyword, "owner": ctx.username},
                headers=_actor_headers(ctx),
            )
            # 优先展示业务系统返回的提示信息（如“无权限 / 无归属客户”），避免把空结果误显示成 {}。
            if isinstance(data, dict) and data.get("message") and not data.get("items"):
                return ok_text(data["message"])
            rows = _rows_from(_unwrap(data))
            return ok_table(rows[0], rows[1:]) if rows else ok_text(_fmt(_unwrap(data)))
        except Exception as e:  # noqa: BLE001
            return fail(f"CRM 查询失败：{e}")
    if settings.MOCK_TOOLS:
        name = keyword or "华为云"
        rows = [["客户", "阶段", "金额(元)", "电话", "邮箱"],
                [name, "商机", 500000, mask_text("13800001111"), mask_text("contact@huawei.com")]]
        return ok_table(rows[0], rows[1:]) if keyword != "无" else ok_text("未查询到属于您的客户记录。")
    return fail("CRM 系统未配置：请设置 CRM_BASE_URL 或开启 MOCK_TOOLS")


# ============================================================
# HR
# ============================================================
async def hr_query(args: dict, ctx: ToolContext) -> ToolResult:
    username = str(args.get("username") or ctx.username or "").strip() or ctx.username
    if settings.HR_BASE_URL:
        try:
            data = await aget(
                settings.HR_BASE_URL.rstrip("/") + "/employees/me",
                token=settings.HR_TOKEN,
                params={"username": username},
                headers=_actor_headers(ctx),
            )
            rec = _unwrap(data)
            if rec is None:
                return ok_text(f"未查询到用户 {username} 的员工档案（或无查看权限）。")
            return ok_text(_fmt(rec))
        except Exception as e:  # noqa: BLE001
            return fail(f"HR 查询失败：{e}")
    if settings.MOCK_TOOLS:
        rows = [["账号", "姓名", "部门", "考勤", "剩余假期"],
                [username, "Demo", ctx.department, "正常", 5]]
        return ok_table(rows[0], rows[1:])
    return fail("HR 系统未配置：请设置 HR_BASE_URL 或开启 MOCK_TOOLS")


# ============================================================
# 财务 ERP
# ============================================================
async def finance_query(args: dict, ctx: ToolContext) -> ToolResult:
    kind = str(args.get("kind") or "invoice").strip()
    if settings.FINANCE_BASE_URL:
        try:
            data = await aget(
                settings.FINANCE_BASE_URL.rstrip("/") + f"/{kind}",
                token=settings.FINANCE_TOKEN,
                headers=_actor_headers(ctx),
            )
            rows = _rows_from(_unwrap(data))
            return ok_table(rows[0], rows[1:]) if rows else ok_text(_fmt(_unwrap(data)))
        except Exception as e:  # noqa: BLE001
            return fail(f"财务查询失败：{e}")
    if settings.MOCK_TOOLS:
        if kind == "revenue":
            return ok_table(["月份", "营收(元)", "成本(元)", "毛利(元)"], [["2026-06", 5100000, 2900000, 2200000]])
        if kind == "expense":
            return ok_table(["类别", "金额(元)", "申请人", "状态"], [["差旅", 12000, "alice", "已报销"]])
        return ok_table(["发票号", "供应商", "金额(元)", "税号", "收款账号"],
                        [["INV-2026-001", "阿里云", 128000, mask_text("91330100MA1A"), mask_text("6222021234567890")]])
    return fail("财务系统未配置：请设置 FINANCE_BASE_URL 或开启 MOCK_TOOLS")


# ============================================================
# OA 审批
# ============================================================
async def oa_start(args: dict, ctx: ToolContext) -> ToolResult:
    flow_type = str(args.get("type") or "请假").strip()
    title = str(args.get("title") or "").strip() or f"{ctx.username}的{flow_type}申请"
    content = str(args.get("content") or "").strip()
    if settings.OA_BASE_URL:
        try:
            data = await apost(
                settings.OA_BASE_URL.rstrip("/") + "/apply",
                token=settings.OA_TOKEN,
                json={"type": flow_type, "applicant": ctx.username, "title": title, "content": content},
                headers=_actor_headers(ctx),
            )
            return ok_text(f"✅ 已真实发起「{flow_type}」审批：{_fmt(_unwrap(data))}")
        except Exception as e:  # noqa: BLE001
            return fail(f"OA 审批发起失败：{e}")
    if settings.MOCK_TOOLS:
        return ok_text(f"✅ 已发起「{flow_type}」审批流程，申请人：{ctx.username}，当前状态：审批中。")
    return fail("OA 系统未配置：请设置 OA_BASE_URL 或开启 MOCK_TOOLS")


async def oa_status(args: dict, ctx: ToolContext) -> ToolResult:
    ap_id = str(args.get("approval_id") or "").strip()
    if not ap_id:
        return fail("缺少必要参数 approval_id")
    if settings.OA_BASE_URL:
        try:
            data = await aget(
                settings.OA_BASE_URL.rstrip("/") + f"/approvals/{ap_id}",
                token=settings.OA_TOKEN,
                headers=_actor_headers(ctx),
            )
            rec = _unwrap(data)
            if rec is None:
                return ok_text(f"未查询到审批单 {ap_id}。")
            return ok_text(_fmt(rec))
        except Exception as e:  # noqa: BLE001
            return fail(f"OA 审批进度查询失败：{e}")
    if settings.MOCK_TOOLS:
        return ok_text(f"审批单 {ap_id}：类型=出差，申请人={ctx.username}，状态=审批中，当前节点=部门主管")
    return fail("OA 系统未配置：请设置 OA_BASE_URL 或开启 MOCK_TOOLS")


def _rows_from(data) -> list[list]:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        cols = list(data[0].keys())
        return [cols, *[[r.get(c) for c in cols] for r in data]]
    return []


ADAPTERS = {
    "crm_query": crm_query,
    "hr_query": hr_query,
    "finance_query": finance_query,
    "oa_start": oa_start,
    "oa_status": oa_status,
}
