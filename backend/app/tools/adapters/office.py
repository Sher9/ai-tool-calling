"""协同办公工具（全员可用）: 飞书 / 企业邮箱 / 在线文档库.

真实接入：在 .env 配置 FEISHU_WEBHOOK_URL / DOC_BASE_URL / MAIL_* 并将
MOCK_TOOLS=false 后，下列适配器发起真实调用；未配置则明确报错，不再返回假数据。
"""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import time
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

from app.config import settings
from app.core.http import aget, apost
from app.core.masking import mask_text
from app.tools.base import ToolContext, ToolResult, fail, ok_table, ok_text


async def feishu_send(args: dict, ctx: ToolContext) -> ToolResult:
    target = args.get("target", "销售群")
    content = args.get("content", "")
    if settings.MOCK_TOOLS:
        return ok_text(f"✅ 已通过飞书向「{target}」发送消息（消息ID: fs_{int(time.time())}）\n内容：{content}")
    if not settings.FEISHU_WEBHOOK_URL:
        return fail("未配置 FEISHU_WEBHOOK_URL，无法真实发送飞书消息，请在 .env 配置自定义机器人 webhook。")
    try:
        # 飞书自定义机器人：text 消息；如需 @ 人群/加签请按官方文档扩展
        await apost(
            settings.FEISHU_WEBHOOK_URL,
            json={"msg_type": "text", "content": {"text": f"【{target}】\n{content}"}},
        )
        return ok_text(f"✅ 已通过飞书真实向「{target}」发送消息。")
    except Exception as e:  # noqa: BLE001
        return fail(f"飞书消息发送失败：{e}")


async def email_query(args: dict, ctx: ToolContext) -> ToolResult:
    keyword = (args.get("keyword") or "").lower()
    limit = int(args.get("limit", 10))
    if settings.MOCK_TOOLS or not settings.MAIL_IMAP_HOST:
        # 演示数据（mock 模式或未配置 IMAP 时）
        _MAILBOX = [
            {"id": 1, "from": "client_a@huake.com", "subject": "Q3 采购意向确认", "date": "2026-07-20"},
            {"id": 2, "from": "vendor@supplier.cn", "subject": "发票已开具", "date": "2026-07-19"},
            {"id": 3, "from": "hr@corp.com", "subject": "季度全员大会通知", "date": "2026-07-18"},
        ]
        rows = [
            [m["id"], mask_text(m["from"]), m["subject"], m["date"]]
            for m in _MAILBOX
            if not keyword or keyword in m["subject"].lower()
        ][:limit]
        if not rows:
            return ok_text("未检索到相关邮件。")
        return ok_table(["ID", "发件人", "主题", "日期"], rows)
    return fail("邮件检索需配置 MAIL_IMAP_HOST 并在 adapters/office.py 实现 IMAP 查询（当前为演示）。")


def _smtp_send(to: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.MAIL_USER
    msg["To"] = to
    with smtplib.SMTP_SSL(settings.MAIL_SMTP_HOST, settings.MAIL_SMTP_PORT) as s:
        s.login(settings.MAIL_USER, settings.MAIL_PASSWORD)
        s.send_message(msg)


async def email_send(args: dict, ctx: ToolContext) -> ToolResult:
    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    if settings.MOCK_TOOLS:
        note = f"附件：{args['attachment_name']}" if args.get("attachment_name") else "无附件"
        return ok_text(f"✅ 邮件已发送（模拟）\n收件人：{to}\n主题：{subject}\n{note}\n正文前 80 字：{body[:80]}")
    if not settings.MAIL_SMTP_HOST:
        return fail("未配置 MAIL_SMTP_HOST，无法真实发送邮件，请在 .env 配置 SMTP。")
    try:
        await asyncio.to_thread(_smtp_send, to, subject, body)
        return ok_text(f"✅ 已真实发送邮件\n收件人：{to}\n主题：{subject}")
    except Exception as e:  # noqa: BLE001
        return fail(f"邮件发送失败：{e}")


def _fmt_online_docs(rows: list) -> str:
    lines = []
    for _tid, title, dept, url in rows:
        lines.append(f"- {title}（{dept or '-'}）\n  {url or ''}")
    return "\n".join(lines) + "\n"


# 检索 query 中的路由/噪音词：这些词用于触发工具，但本身不是检索意图，
# 带入 RAG 会稀释相似度（如「知识库 安全管理制度」里的「知识库」）。
_KB_QUERY_NOISE = [
    "知识库", "检索", "查询", "查看", "搜索", "查一下", "找一下", "找", "帮我查",
    "帮我检索", "请查", "请问", "我想知道", "我需要", "我想了解", "关于", "相关的",
    "资料", "库里", "库中", "文档库", "在文档里", "里面",
]


def _clean_kb_query(q: str) -> str:
    s = q
    for w in _KB_QUERY_NOISE:
        s = s.replace(w, "")
    s = re.sub(r"\s+", " ", s).strip()
    return s or q.strip()  # 去噪后为空则回退原文，避免检索词丢失


async def doc_search(args: dict, ctx: ToolContext) -> ToolResult:
    """知识库检索：优先检索内部 RAG 知识库，未命中再回退语雀/Confluence 在线文档库。

    检索策略：
    1. 优先对内部 RAG 知识库做向量检索（vector_search），命中即返回；
    2. 仅当 RAG 未命中，或用户显式指定外部文档库（含「语雀 / confluence / 在线文档 / 文档库」）
       时，才回退到外部在线文档库（DOC_BASE_URL）。
    """
    keyword = (args.get("keyword") or "").strip().lower()
    if not keyword:
        return fail("缺少 keyword 参数")

    explicit_external = any(s in keyword for s in ("语雀", "confluence", "在线文档", "文档库"))
    # 去除路由/噪音词，得到纯检索意图（如「知识库 安全管理制度」→「安全管理制度」）
    clean = _clean_kb_query(keyword)

    # 1) 优先检索内部 RAG 知识库
    if not explicit_external:
        try:
            from app.agent.rag import retrieve
            from app.db.base import async_session_maker
            from app.tools.adapters.knowledge import vector_search as _rag_vector_search

            async with async_session_maker() as session:
                chunks = await retrieve(session, query=clean, department=ctx.department,
                                        limit=6, user_id=ctx.user_id, include_episodic=False)

            if chunks:
                # 标题/制度名命中（如问「安全管理制度」命中了同名文档）：
                # 直接定位到该文档并给出章节摘要，而不是把整段正文灌回模型导致答非所问
                title_hit = None
                for c in chunks:
                    t = (c.get("title") or "").lower()
                    if t and t.strip() == clean.strip():
                        title_hit = c
                        break
                if title_hit:
                    meta = title_hit.get("meta", {}) or {}
                    src = meta.get("source") or title_hit.get("title") or "未知"
                    loc = f"（来源：{src}"
                    if meta.get("page"):
                        loc += f"｜页码：{meta['page']}"
                    if meta.get("section"):
                        loc += f"｜章节：{meta['section']}"
                    loc += "）"
                    head = (f"【检索来源：内部 RAG 知识库】\n"
                            f"已为你定位到制度文档《{title_hit.get('title')}》{loc}。"
                            f"如需查看具体条款，请针对该制度提出更具体的问题（如「安全管理制度中的违规处罚条款」）。")
                    return ok_text(head)
                # 否则走常规向量检索（已内置答案抽取，仅返回最相关片段）
                rag = await _rag_vector_search({"query": clean}, ctx)
                if rag and rag.ok and rag.text and "未检索到" not in rag.text:
                    return ok_text("【检索来源：内部 RAG 知识库】\n" + rag.text)
        except Exception as e:  # noqa: BLE001
            logger.warning("RAG 知识库检索失败，回退在线文档库：%s", e)

    # 2) 回退：外部在线文档库（语雀 / Confluence）
    if settings.MOCK_TOOLS or not settings.DOC_BASE_URL:
        _DOCS = [
            {"id": 1, "title": "新员工入职手册", "dept": "general", "url": "yuque://doc/onboarding"},
            {"id": 2, "title": "销售提成制度 v3", "dept": "sales", "url": "yuque://doc/sales-commission"},
            {"id": 3, "title": "后端服务架构设计", "dept": "tech", "url": "confluence://doc/backend-arch"},
            {"id": 4, "title": "财务报销规范", "dept": "finance", "url": "yuque://doc/expense-policy"},
        ]
        visible = [d for d in _DOCS if d["dept"] in (ctx.department, "general")]
        rows = [
            [d["id"], d["title"], d["dept"], d["url"]]
            for d in visible
            if not keyword or keyword in d["title"].lower()
        ]
        note = "【检索来源：在线文档库（语雀/Confluence）· 演示数据】"
        if not rows:
            return ok_text(note + "\n未检索到相关在线文档。")
        return ok_text(note + "\n" + _fmt_online_docs(rows))
    try:
        base = settings.DOC_BASE_URL.rstrip("/")
        is_confluence = "confluence" in base.lower() or "/rest/api" in base.lower() \
            or "/wiki" in base.lower()
        if is_confluence:
            # Confluence REST API：GET /rest/api/content/search?cql=siteSearch ~ "关键字"
            data = await aget(
                base + "/search",
                token=settings.DOC_TOKEN,
                params={"cql": f'siteSearch ~ "{keyword}"', "limit": 20},
            )
        else:
            # 语雀等：POST /search/ 并带 JSON body
            data = await apost(base + "/search/", token=settings.DOC_TOKEN,
                               json={"keyword": keyword, "department": ctx.department})
        # 兼容多种返回形态：list[dict] / {"data": [...]} / {"results": [...]} / 纯文本
        items: list = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Confluence 用 results；语雀常见 data / results / items / list / docs
            for key in ("results", "data", "items", "list", "docs", "documents"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
            else:
                items = [data]
        elif isinstance(data, str):
            # 非 JSON 文本（如 HTML 登录页 / 服务报错页），给出可操作的提示
            snippet = data.strip()[:200]
            if "<html" in snippet.lower() or "<!doctype" in snippet.lower():
                return fail(
                    "文档检索失败：在线文档库返回了 HTML 页面（疑似未鉴权或地址错误）。\n"
                    f"请确认：1) DOC_BASE_URL 指向 OpenAPI 检索地址（Confluence 应为 .../rest/api/content/search）；"
                    f"2) DOC_TOKEN 有效。响应片段：{snippet}"
                )
            return fail(f"文档检索失败：在线文档库返回非结构化内容（疑似未返回 JSON）。"
                        f"请确认 DOC_BASE_URL 指向正确的检索接口。响应片段：{snippet}")
        rows = []
        for d in items:
            if isinstance(d, dict):
                # 兼容 Confluence 的嵌套字段（title 可能是字符串或 {"title": ...}）
                title = d.get("title")
                if isinstance(title, dict):
                    title = title.get("title")
                # Confluence 的链接在 _links.self / tinyui
                url = (d.get("url") or (d.get("_links") or {}).get("webui")
                       or (d.get("_links") or {}).get("tinyui") or "")
                if url and not str(url).startswith("http"):
                    url = base.rsplit("/rest", 1)[0] + url
                rows.append([d.get("id") or (d.get("content") or {}).get("id"), title,
                             d.get("department") or (d.get("space") or {}).get("key"), url])
            elif isinstance(d, str):
                rows.append([None, d, ctx.department, None])
        note = "【检索来源：在线文档库（语雀/Confluence）】"
        return ok_text(note + "\n" + _fmt_online_docs(rows)) if rows else ok_text(note + "\n未检索到相关在线文档。")
    except Exception as e:  # noqa: BLE001
        return fail(f"文档检索失败：RAG 知识库与在线文档库均不可用（{type(e).__name__}: {e}）")


async def meeting_minutes(args: dict, ctx: ToolContext) -> ToolResult:
    text = args.get("text", "")
    if not text:
        return ok_text("【会议纪要】\n1. 确定本周迭代目标；\n2. 风险：联调环境不稳定；\n3. 行动项：张三负责修复登录接口。")
    return ok_text("【AI 提取的会议纪要】\n" + "\n".join(f"- {line.strip()}" for line in text.splitlines() if line.strip()))


ADAPTERS = {
    "feishu_send": feishu_send,
    "email_query": email_query,
    "email_send": email_send,
    "doc_search": doc_search,
    "meeting_minutes": meeting_minutes,
}
