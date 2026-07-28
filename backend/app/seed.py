"""Initial data seeding: demo users, tool registry, prompt templates.

Run automatically on startup if the database is empty. Idempotent.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import AuditLog, PromptTemplate, Tool, User

USERS = [
    ("admin", "平台管理员", "admin123", "admin", "general"),
    ("alice", "Alice（销售）", "alice123", "sales", "sales"),
    ("bob", "Bob（销售）", "bob123", "sales", "sales"),
    ("carol", "Carol（研发）", "carol123", "tech", "tech"),
    ("dave", "Dave（财务）", "dave123", "finance", "finance"),
    ("erin", "Erin（人事）", "erin123", "hr", "hr"),
]

# tool definitions: name, display_name, category, description, adapter, allowed_roles,
#                   mask_sensitive, requires_internet, parameters
TOOLS = [
    # ---- 基础通用查询工具 ----
    ("get_current_time", "当前时间/时区", "general", "获取当前日期、星期、时间、时间戳，支持指定时区", "get_current_time", [], False, False,
     {"type": "object", "properties": {"timezone": {"type": "string", "description": "IANA 时区名，如 Asia/Shanghai、America/New_York"}}, "required": []}),
    ("math_calculate", "数学表达式计算", "general", "求解数学表达式（四则/幂/开方/三角函数），避免 LLM 直接算数产生幻觉", "math_calculate", [], False, False,
     {"type": "object", "properties": {"math_expression": {"type": "string", "description": "如 (1+2)*3/sqrt(9) 或 pow(2,10)"}}, "required": ["math_expression"]}),


    # ---- 办公工具 ----
    ("feishu_send", "飞书消息发送", "office", "通过飞书发送消息到群或个人", "feishu_send", [], False, False,
     {"type": "object", "properties": {"target": {"type": "string"}, "content": {"type": "string"}}, "required": ["content"]}),
    ("email_query", "企业邮件检索", "office", "检索业务往来邮件", "email_query", [], True, False,
     {"type": "object", "properties": {"keyword": {"type": "string"}, "limit": {"type": "integer"}}}),
    ("email_send", "企业邮件发送", "office", "发送邮件（可带附件）", "email_send", [], True, False,
     {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}),
    ("doc_search", "知识库检索", "office", "知识库检索：优先检索内部 RAG 知识库，未命中再回退语雀/Confluence 在线文档库", "doc_search", [], False, False,
     {"type": "object", "properties": {"keyword": {"type": "string"}}}),
    ("meeting_minutes", "会议纪要提取", "office", "从会议记录提取结构化纪要", "meeting_minutes", [], False, False,
     {"type": "object", "properties": {"text": {"type": "string"}}}),

     # ---- 开发工具 ----
    ("github_search_repo", "GitHub 仓库检索", "dev", "按关键词搜索 GitHub 仓库基础信息，或列出某仓库的所有分支（公开只读，所有登录用户可用）", "github_search_repo", [], False, False,
     {"type": "object", "properties": {"keyword": {"type": "string", "description": "搜索仓库的关键词"}, "repo": {"type": "string", "description": "指定仓库 owner/name，列出其所有分支"}}, "required": []}),
    ("swagger_parse", "接口文档解析", "dev", "解析 Swagger 并生成调用示例", "swagger_parse", ["tech", "admin"], False, False,
     {"type": "object", "properties": {"path": {"type": "string"}, "method": {"type": "string"}}}),
    # ---- Git / 研发效能工具 ----
    ("git_weekly_report", "Git 周报生成", "dev", "读取 GitHub 某仓库的提交记录，按 conventional-commit 类型分类汇总，生成 Markdown 周报（支持作者/分支/时间范围过滤）", "git_weekly_report", ["tech", "admin"], False, False,
     {"type": "object", "properties": {"repo_path": {"type": "string", "description": "相对沙箱根目录的 Git 仓库路径，默认当前仓库"}, "author": {"type": "string", "description": "仅统计该作者的提交，留空表示全部"}, "branch": {"type": "string", "description": "指定分支名（如 main），留空默认 HEAD"}, "since": {"type": "string", "description": "起始日期 YYYY-MM-DD，默认最近 7 天前"}, "until": {"type": "string", "description": "结束日期 YYYY-MM-DD，默认今天"}}, "required": []}),


   # ---- 业务工具 ----
    ("crm_query", "CRM 客户查询", "business", "查询客户/商机/跟进（行权限隔离）", "crm_query", ["sales", "admin"], True, False,
     {"type": "object", "properties": {"keyword": {"type": "string"}}}),
    ("hr_query", "HR 人事查询", "business", "查询考勤/假期/简历（仅本人）", "hr_query", ["hr", "admin"], True, False,
     {"type": "object", "properties": {}}),
    ("finance_query", "财务 ERP 查询", "business", "查询报销/发票/营收（财务岗）", "finance_query", ["finance", "admin"], True, False,
     {"type": "object", "properties": {"kind": {"type": "string", "enum": ["invoice", "revenue"]}}}),
    ("oa_start", "OA 审批发起", "business", "发起出差/采购/请假审批", "oa_start", [], False, False,
     {"type": "object", "properties": {"type": {"type": "string"}}}),
    ("oa_status", "OA 审批进度", "business", "查询审批流程进度", "oa_status", [], False, False,
     {"type": "object", "properties": {"approval_id": {"type": "string"}}}),


    # ---- 计算工具 ----
    ("chart_generate", "图表生成", "compute", "折线/柱状/Mermaid 流程图", "chart_generate", [], False, False,
     {"type": "object", "properties": {"type": {"type": "string"}, "title": {"type": "string"}, "labels": {"type": "array"}, "values": {"type": "array"}, "code": {"type": "string"}}}),
    ("currency_convert", "汇率换算", "compute", "多币种汇率换算", "currency_convert", [], False, False,
     {"type": "object", "properties": {"amount": {"type": "number"}, "from": {"type": "string"}, "to": {"type": "string"}}}),
    ("worktime_cost", "工时成本换算", "compute", "工时×费率成本测算", "worktime_cost", [], False, False,
     {"type": "object", "properties": {"hours": {"type": "number"}, "hourly_rate": {"type": "number"}}}),


    # ---- 自研工具 ----
    ("inventory_query", "库存查询", "custom", "查询库存（自研接口）", "inventory_query", [], False, False,
     {"type": "object", "properties": {"keyword": {"type": "string"}}}),
    ("product_param", "产品参数查询", "custom", "查询产品参数（自研接口）", "product_param", [], False, False,
     {"type": "object", "properties": {"model": {"type": "string"}}}),
    ("quote_generate", "客户报价单生成", "custom", "生成客户报价单（自研接口）", "quote_generate", [], False, False,
     {"type": "object", "properties": {"items": {"type": "array"}}}),
    
    # ---- 外网查询工具 ----
    ("weather_query", "天气查询（外网）", "external", "查询天气（默认关闭）", "weather_query", [], False, True,
     {"type": "object", "properties": {"city": {"type": "string"}}}),
    ("calendar_query", "日历查询（外网）", "external", "查询日历日程（默认关闭）", "calendar_query", [], False, True,
     {"type": "object", "properties": {"date": {"type": "string"}}}),
    ("whois_query", "域名/IP 查询（外网）", "external", "域名或 IP 查询（默认关闭）", "whois_query", [], False, True,
     {"type": "object", "properties": {"domain": {"type": "string"}}}),
    ("web_search", "公开资料检索（外网）", "external", "行业公开资料检索（默认关闭）", "web_search", [], False, True,
     {"type": "object", "properties": {"query": {"type": "string"}}}),

    # ---- RAG 知识库 & 数据库工具（企业 Agent 核心） ----
    ("vector_search", "知识库向量检索", "rag", "从企业知识库向量检索相关文档片段，支持权限/标签过滤，用于生成答案引用", "vector_search", [], False, False,
     {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "description": "返回片段数，默认 5"}, "metadata_filter": {"type": "object", "description": "如 {\"doc_types\":[\"manual\"]}"}}, "required": ["query"]}),

    # ---- 文件 & 系统操作工具（本地/客户端 Agent） ----
]

PROMPTS = [
    ("system", "系统提示词",
     "你是企业内部私有化部署的 AI Agent 助手。你只能调用已授权工具完成任务，"
     "严禁泄露用户隐私数据，所有对外输出需符合公司安全规范。"),
    ("planner", "任务规划提示词",
     "请将用户的复杂办公请求拆解为可顺序或并行执行的工具调用步骤；"
     "优先检索其权限范围内的企业知识库以减少幻觉。"),
]


async def seed_initial_data(session) -> None:
    # 用户/提示词仅在首次（users 表为空）全量写入；工具注册表则每次启动增量同步，
    # 保证旧库也能补齐新增/曾被删除的工具，无需清空数据库重灌。
    existing_user = (await session.execute(select(User))).scalars().first()
    if not existing_user:
        for username, name, pwd, role, dept in USERS:
            session.add(User(username=username, display_name=name, password_hash=hash_password(pwd),
                             role=role, department=dept))

    # ---- 工具注册表：按 name upsert（存在则同步最新定义并启用，缺失则插入） ----
    seeded = (await session.execute(select(Tool))).scalars().all()
    by_name = {t.name: t for t in seeded}
    for name, dn, cat, desc, adapter, roles, mask, net, params in TOOLS:
        if name in by_name:
            t = by_name[name]
            t.display_name = dn
            t.category = cat
            t.description = desc
            t.adapter = adapter
            t.allowed_roles = roles
            t.mask_sensitive = mask
            t.requires_internet = net
            t.parameters = params
            t.enabled = True  # 定义存在即视为启用，避免历史停用状态阻断意图
        else:
            session.add(Tool(name=name, display_name=dn, category=cat, description=desc, adapter=adapter,
                             allowed_roles=roles, mask_sensitive=mask, requires_internet=net,
                             parameters=params, enabled=True))

    # ---- 提示词模板：缺则补种（不覆盖已有） ----
    prompt_keys = {p.key for p in (await session.execute(select(PromptTemplate))).scalars().all()}
    for key, title, content in PROMPTS:
        if key not in prompt_keys:
            session.add(PromptTemplate(key=key, title=title, content=content))

    session.add(AuditLog(action="system", resource="seed", detail={"note": "seed synced"}))
    await session.commit()
