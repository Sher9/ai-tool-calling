"""任务规划器 Planner (层级 3.3, LangGraph 编排).

Two reasoning modes (auto-switched):
  - simple task  -> single tool function-call
  - complex task -> decompose into a chain of steps (serial / parallel)

When MOCK_LLM is on we use a deterministic intent matcher so the system runs
without a model. With a real model, `plan_query_llm` parses tool_calls into the
same plan shape.
"""
from __future__ import annotations

import asyncio
from typing import Callable

from app.agent.llm import chat
from app.tools.base import ToolContext


def _step(tool: str, args: dict, display: str) -> dict:
    return {"tool": tool, "args": args, "display": display}


# Each detector: (matcher(query)->bool, builder(query, ctx)->step|None)
def _detectors() -> list[tuple[Callable[[str], bool], Callable[[str, ToolContext], dict | None]]]:
    def has(*keys):
        return lambda q: any(k in q for k in keys)

    def b_sales(q, ctx):
        return _step("crm_query", {"keyword": "本月"}, "统计本月销售数据")

    def b_chart(q, ctx):
        # 解析图表类型：优先按用户表述判定，默认柱状图
        if any(w in q for w in ("折线图", "走势图", "趋势图")):
            ctype = "line"
        elif any(w in q for w in ("饼图", "占比", "比例图", "扇形图")):
            ctype = "pie"
        elif any(w in q for w in ("柱状图", "条形图", "柱形图", "直方图")):
            ctype = "bar"
        else:
            ctype = "bar"  # 默认柱状图（“画成图/画图表”未明确类型时）

        # 解析数值数组：[12,19,8,23] 或 “12 19 8 23”
        import re as _re
        nums = []
        am = _re.search(r"\[([\d.,\s\-]+)\]", q)
        if am:
            nums = [float(x) for x in _re.split(r"[,\s]+", am.group(1).strip()) if x.strip() != ""]
        else:
            nums = [float(x) for x in _re.findall(r"-?\d+(?:\.\d+)?", q)]
        # 过滤掉明显属于“年份/序号/坐标”的噪声：若同时出现成对坐标(x,y)，这里不做复杂处理
        values = nums[:12] if nums else [12, 19, 15, 22]
        labels = [str(i + 1) for i in range(len(values))]
        title = "数据图表" if ctype != "line" else "数据趋势"
        return _step("chart_generate", {"type": ctype, "title": title,
                                        "labels": labels, "values": values}, "生成图表")

    def b_feishu(q, ctx):
        return _step("feishu_send", {"target": "销售群", "content": "本月销售数据已汇总，见趋势图。"}, "发送到销售群")

    def b_email_send(q, ctx):
        # 从用户原句解析真实收件人邮箱（避免写死 team@corp.com 导致发错人）
        import re as _re
        m = _re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]+", q)
        to = m.group(0) if m else ""
        # 主题：优先取“主题「xxx」/主题：xxx”，否则取去掉触发词后的前半句
        sm = _re.search(r"主题[是为：:\s]*[「\"']?([^「\"'」，,。.\n]{1,40})", q)
        subject = sm.group(1).strip("「\"'」 ") if sm else q.replace("给", "").replace("发邮件", "").replace("发送邮件", "").replace("邮件通知", "").strip()[:20]
        # 正文：优先提取「内容：xxx」（到句末）；否则去掉邮箱/主题/触发词后的残段；
        # 都没有则留空，绝不可把整句原话当正文发送
        bm = _re.search(r"内容[是为：:\s]*([\s\S]+)$", q)
        if bm:
            body = bm.group(1).strip()
        else:
            rest = q
            if to:
                rest = rest.replace(to, "")
            rest = _re.sub(r"主题[是为：:\s]*[「\"']?[^「\"'」，,。.\n]{1,40}", "", rest)
            rest = (rest.replace("发邮件", "").replace("发送邮件", "").replace("邮件通知", "")
                        .replace("给", "").replace("，", "").replace(",", ""))
            body = _re.sub(r"^内容[：:]\s*", "", rest.strip())
        return _step("email_send", {"to": to, "subject": subject, "body": body}, "发送邮件")

    def b_email_query(q, ctx):
        return _step("email_query", {"keyword": ""}, "检索业务邮件")

    def b_doc_search(q, ctx):
        return _step("doc_search", {"keyword": q[:10]}, "检索知识库文档")

    def b_meeting(q, ctx):
        return _step("meeting_minutes", {"text": ""}, "提取会议纪要")

    def b_code(q, ctx):
        # 从用户原句提取仓库关键词 / 指定仓库（owner/name）
        import re as _re
        repo = ""
        rm = _re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", q)
        if rm:
            repo = rm.group(1)
        # 清洗噪声词，保留真实检索关键词（如 ai-code）。
        # 注意：不能只 replace("搜")，否则"搜一下 ai-code 相关的仓库"会残留"一下...相关的"。
        _noise = ["搜一下", "搜索一下", "搜素", "搜", "一下", "相关", "的", "仓库", "分支",
                  "代码检索", "代码仓库", "查代码", "查仓库", "搜仓库", "列分支", "github", "GitHub",
                  "查", "上", "这个", "一个", "有", "什么", "哪个", "看看", "帮我", "请", "在"]
        kw = q
        for w in _noise:
            kw = kw.replace(w, " ")
        kw = _re.sub(r"\s+", " ", kw).strip()[:40]
        # 若清洗后仍为空（例如原句就是"搜仓库"），尝试提取英文/连字符词作为兜底
        if not kw and not repo:
            em = _re.search(r"([A-Za-z0-9][A-Za-z0-9_-]{1,39})", q)
            kw = em.group(1) if em else ""
        return _step("github_search_repo", {"keyword": kw, "repo": repo}, "检索 GitHub 仓库/分支")

    def b_swagger(q, ctx):
        # 命中「接口 /api /swagger /openapi」任一即路由，并从 query 抽取路径与方法
        if not any(w in q for w in ("接口", "/api", "swagger", "Swagger", "openapi", "OpenAPI", "api")):
            return None
        import re as _re
        pm = _re.search(r"(/[^\s，。、]+)", q)
        path = pm.group(1) if pm else "/api/v1/users"
        if any(w in q for w in ("post", "POST", "新增", "创建", "提交")):
            method = "POST"
        elif any(w in q for w in ("put", "PUT", "修改", "更新")):
            method = "PUT"
        elif any(w in q for w in ("delete", "DELETE", "删除")):
            method = "DELETE"
        else:
            method = "GET"
        return _step("swagger_parse", {"path": path, "method": method}, "解析接口文档")

    def b_crm(q, ctx):
        # 提取客户名称关键字：把“我的客户张三 / 客户 张三 / 张三的客户 / 名为王五”中的客户名解析出来，
        # 避免直接传空 keyword 导致返回全部客户。单遍正则，按优先级匹配。
        import re as _re
        pats = [
            r"客户\s*[：: ]?\s*([\u4e00-\u9fa5]{2,4})",          # 客户张三 / 客户：李四
            r"([\u4e00-\u9fa5]{2,4})\s*的客户",                  # 张三的客户
            r"(?:名为|叫|姓名[是为：: ]*)\s*([\u4e00-\u9fa5]{2,4})",  # 名为王五 / 叫张三
        ]
        name = ""
        for p in pats:
            m = _re.search(p, q)
            if m:
                name = m.group(1)
                break
        return _step("crm_query", {"keyword": name}, "查询客户/商机")

    def b_hr(q, ctx):
        return _step("hr_query", {}, "查询人事数据")

    def b_finance(q, ctx):
        return _step("finance_query", {"kind": "invoice"}, "查询财务/发票")

    def b_oa_start(q, ctx):
        return _step("oa_start", {"type": "请假"}, "发起 OA 审批")

    def b_oa_status(q, ctx):
        return _step("oa_status", {"approval_id": "AP-1001"}, "查询审批进度")

    def b_currency(q, ctx):
        # 命中汇率词或「X 币 + 能换/折合 + Y 币」结构即路由
        if not ("汇率" in q or "换" in q or "兑换" in q or "折合" in q):
            return None
        if not any(c in q for c in ("人民币", "美元", "日元", "欧元", "cny", "usd", "eur", "jpy", "元", "币")):
            return None
        import re as _re
        am = _re.search(r"(\d+(?:\.\d+)?)", q)
        amount = float(am.group(1)) if am else 1.0
        frm = "USD" if any(w in q for w in ("美元", "usd", "$")) else (
            "EUR" if any(w in q for w in ("欧元", "eur")) else (
                "JPY" if any(w in q for w in ("日元", "jpy")) else "USD"))
        to = "CNY" if any(w in q for w in ("人民币", "cny", "元")) else "USD"
        return _step("currency_convert", {"amount": amount, "from": frm, "to": to}, "汇率换算")

    def b_worktime(q, ctx):
        return _step("worktime_cost", {"hours": 40, "hourly_rate": 200}, "工时成本换算")

    def b_mermaid(q, ctx):
        # 把用户描述的流程意图作为 mermaid 文案交给 chart_generate，由工具再润色为标准语法
        return _step("chart_generate", {"type": "mermaid", "title": q[:30],
                                        "code": q}, "生成流程图")

    def b_inventory(q, ctx):
        # 仅当明确表达“查看全部库存”时才传空 keyword（返回全部）；
        # 其余情况（如“交换机 S100 库存”）提取商品关键字做精确检索。
        import re as _re
        _all_phrases = ("查所有库存", "所有库存", "查全部库存", "全部库存", "查询所有库存", "库存一览", "库存列表")
        is_all = q.strip() in ("库存", "查库存") or any(p in q for p in _all_phrases)
        if is_all:
            kw = ""
        else:
            # 去掉触发词与噪声，保留商品名（如“交换机 S100”“主机 X1”）
            _noise = ["查一下", "查", "一下", "搜索", "搜索一下", "搜", "看", "看看",
                      "的", "有", "什么", "哪个", "多少", "还剩", "剩余", "库存", "量", "在"]
            kw = q
            for w in _noise:
                kw = kw.replace(w, " ")
            kw = _re.sub(r"\s+", " ", kw).strip()
            # 兜底：若清洗后为空（例如原句就是“查库存”），视为查全部
            if not kw:
                kw = ""
        return _step("inventory_query", {"keyword": kw}, "查询库存")

    def b_quote(q, ctx):
        # 解析“给客户生成报价单，含 交换机 S100 10台、主机 X1 5台”这类明细。
        # 每一条形如 <产品名/型号> <数量>台/个/套，可能有多条（用 、/，/和 分隔）。
        import re as _re
        items = []
        # 以中文顿号/逗号/“和”“以及”切分条目
        parts = _re.split(r"[、，,；;]|和|以及|包括|包含", q)
        for part in parts:
            # 数量：必须是“数字+单位(台/个/套/件)”形式，避免误匹配型号里的数字（如 S100）
            qm = _re.search(r"(\d+)\s*(?:台|个|套|件)", part)
            qty = int(qm.group(1)) if qm else 1
            # 产品型号（ASCII 型号令牌，支持 “X2 Pro” 这类带空格的）
            mm = _re.search(r"[A-Za-z]+[0-9][A-Za-z0-9._-]*(?:\s+[A-Za-z][A-Za-z0-9._-]*)?", part)
            if not mm:
                # 没有型号令牌则跳过（如“给客户生成报价单”本身）
                continue
            model = mm.group(0).strip()
            # 产品展示名：去掉数量词与触发词后的整段
            name = part
            name = _re.sub(r"\d+\s*(?:台|个|套|件)", "", name)
            for w in ("查一下", "查", "生成报价单", "报价单", "报价", "生成", "含",
                      "的", "产品", "请", "帮我", "给", "客户", "给客户"):
                name = name.replace(w, " ")
            name = _re.sub(r"\s+", " ", name).strip().lstrip("：:，,、 ") or model
            items.append({"name": name, "model": model, "qty": qty})
        if not items:
            # 兜底：整句里提取不到明细时，尝试直接抓“型号+数量(带单位)”
            qm = _re.search(r"(\d+)\s*(?:台|个|套|件)", q)
            qty = int(qm.group(1)) if qm else 1
            mm = _re.search(r"[A-Za-z]+[0-9][A-Za-z0-9._-]*(?:\s+[A-Za-z][A-Za-z0-9._-]*)?", q)
            if mm:
                items.append({"name": mm.group(0).strip(), "model": mm.group(0).strip(), "qty": qty})
        return _step("quote_generate", {"items": items, "customer": ""}, "生成报价单")

    def b_product(q, ctx):
        # 产品路由：
        #  - 明确表达“查看全部/所有产品”且无型号时，传空 model（查全部产品列表）；
        #  - 否则提取产品型号（如“交换机 S100”→S100，“主机 X2 Pro”→X2 Pro），不能写死 X1。
        import re as _re
        # 先看是否为“查全部产品”类意图（无具体型号）
        _all_phrases = ("查所有产品", "所有产品", "查全部产品", "全部产品", "查询所有产品",
                        "产品一览", "产品列表", "产品大全")
        is_all = q.strip() in ("产品", "查产品") or any(p in q for p in _all_phrases)
        m = _re.search(r"[A-Za-z]+[0-9][A-Za-z0-9._-]*(?:\s+[A-Za-z][A-Za-z0-9._-]*)?", q)
        if is_all and not m:
            return _step("product_param", {"model": ""}, "查询全部产品")
        if m:
            return _step("product_param", {"model": m.group(0).strip()}, "查询产品参数")
        # 兜底：去掉触发词，剩余作为产品名尝试
        _noise = ["查一下", "查", "一下", "搜索", "搜", "看", "看看", "的",
                  "产品参数", "参数", "产品", "规格", "配置", "有", "什么", "多少", "在"]
        kw = q
        for w in _noise:
            kw = kw.replace(w, " ")
        kw = _re.sub(r"\s+", " ", kw).strip()
        return _step("product_param", {"model": kw}, "查询产品参数")

    def _extract_city(q: str) -> str:
        # 从问句中 stripping 常见修饰词与“天气”关键词，剩余即城市名
        city = q
        for w in ("天气", "查", "查询", "请问", "帮我", "一下", "的", "现在", "今天",
                  "当前", "多少", "怎么样", "如何", "吗", "呢", "？", "?", "。",
                  "，", ",", "、", " ", " "):
            city = city.replace(w, "")
        return city.strip() or "北京"

    def b_weather(q, ctx):
        return _step("weather_query", {"city": _extract_city(q)}, "查询天气")

    def b_calendar(q, ctx):
        return _step("calendar_query", {"date": "今天"}, "查询日历")

    def b_whois(q, ctx):
        return _step("whois_query", {"domain": "corp.com"}, "域名/IP 查询")

    def b_web(q, ctx):
        # 若查询涉及「仓库/分支/GitHub」等代码检索意图，交由 b_code 处理，避免与通用网页搜索混淆
        if any(w in q for w in ("仓库", "分支", "github", "GitHub", "代码检索", "搜仓库", "查仓库", "列分支")):
            return None
        from app.tools.adapters.external import _clean_query
        return _step("web_search", {"query": _clean_query(q)}, "公开资料检索")

    def b_feishu_send(q, ctx):
        return _step("feishu_send", {"target": "销售群", "content": q[:50]}, "发送飞书消息")

    def b_time(q, ctx):
        # 从问句提取城市并映射到 IANA 时区，否则回退上海；避免「纽约几点」仍返回上海时间
        _CITY_TZ = {
            "纽约": "America/New_York", "洛杉矶": "America/Los_Angeles", "旧金山": "America/Los_Angeles",
            "芝加哥": "America/Chicago", "多伦多": "America/Toronto", "温哥华": "America/Vancouver",
            "伦敦": "Europe/London", "巴黎": "Europe/Paris", "柏林": "Europe/Berlin", "莫斯科": "Europe/Moscow",
            "东京": "Asia/Tokyo", "首尔": "Asia/Seoul", "新加坡": "Asia/Singapore", "香港": "Asia/Hong_Kong",
            "北京": "Asia/Shanghai", "上海": "Asia/Shanghai", "深圳": "Asia/Shanghai", "广州": "Asia/Shanghai",
            "悉尼": "Australia/Sydney", "墨尔本": "Australia/Melbourne", "迪拜": "Asia/Dubai",
            "孟买": "Asia/Kolkata", "圣保罗": "America/Sao_Paulo", "墨西哥城": "America/Mexico_City",
        }
        tz = "Asia/Shanghai"
        city = ""
        for c, zone in _CITY_TZ.items():
            if c in q:
                tz = zone
                city = c
                break
        return _step("get_current_time", {"timezone": tz, "city": city}, "获取当前时间")

    def b_math(q, ctx):
        from app.tools.adapters.general import _clean_math_expr
        return _step("math_calculate", {"math_expression": _clean_math_expr(q)}, "数值计算")

    def b_git_weekly(q, ctx):
        # 解析 GitHub 仓库（owner/name）、作者、分支、时间范围
        import re as _re
        repo = ""
        rm = _re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", q)
        if rm:
            repo = rm.group(1)
        author = ""
        am = _re.search(r"(?:作者|author)[是为：: ]*([A-Za-z0-9_.-]{2,30})", q, _re.IGNORECASE)
        if am:
            author = am.group(1)
        branch = ""
        bm = _re.search(r"(?:分支|branch)[是为：: ]*([A-Za-z0-9_./-]{2,40})", q, _re.IGNORECASE)
        if bm:
            branch = bm.group(1)
        since = until = None
        dm = _re.search(r"(\d{4}-\d{2}-\d{2})\s*[~到至至-]\s*(\d{4}-\d{2}-\d{2})", q)
        if dm:
            since, until = dm.group(1), dm.group(2)
        return _step("git_weekly_report",
                     {"repo": repo, "author": author, "branch": branch,
                      "since": since, "until": until}, "生成 Git 周报")

    def b_vector(q, ctx):
        return _step("vector_search", {"query": q[:20], "top_k": 5}, "向量语义检索")

    def b_code_explain(q, ctx):
        return _step("code_explain", {"code": "def f(x): return x*2"}, "解释代码逻辑")

    def b_bug(q, ctx):
        return _step("bug_analyze", {"desc": q[:50]}, "分析定位缺陷")

    rules = [
        (has("统计", "本月销售", "销售数据", "业绩"), b_sales),
        (has("excel", "Excel", "趋势图", "折线图", "柱状图", "条形图", "饼图", "画成", "画图表", "绘制", "数据图", "图表"), b_chart),
        (has("发送销售群", "发到群", "销售群", "发飞书", "飞书"), b_feishu_send),
        (has("发邮件", "发送邮件", "邮件通知"), b_email_send),
        (has("查邮件", "检索邮件", "业务往来邮件", "邮件"), b_email_query),
        (has("知识库", "检索文档", "查文档", "文档", "在线文档", "语雀", "confluence", "文档库"), b_doc_search),
        (has("纪要", "会议纪要"), b_meeting),
        (has("代码片段", "查代码", "代码仓库", "搜索代码", "仓库", "分支", "github", "GitHub", "搜仓库", "查仓库", "列分支"), b_code),
        (has("接口文档", "接口示例", "swagger", "Swagger", "接口", "/api", "openapi", "OpenAPI", "api 文档", "解析接口"), b_swagger),
        (has("客户", "商机", "跟进记录", "CRM"), b_crm),
        (has("考勤", "假期", "薪资", "简历", "招聘", "人事"), b_hr),
        (has("报销", "发票", "营收", "财务报表", "财务"), b_finance),
        (has("审批进度", "审批状态", "进度查询"), b_oa_status),
        (has("发起审批", "出差", "请假", "采购流程", "审批"), b_oa_start),
        (has("汇率", "美元", "人民币", "日元", "欧元", "外币", "兑换", "折合", "换汇", "汇率换算"), b_currency),
        (has("工时", "成本测算", "测算"), b_worktime),
        (has("画流程图", "流程图", "mermaid", "架构图", "时序图"), b_mermaid),
        (has("流程图", "mermaid", "Mermaid"), b_mermaid),
        (has("库存"), b_inventory),
        (has("报价单", "报价"), b_quote),
        (has("产品", "产品参数"), b_product),
        (has("天气"), b_weather),
        (has("日历", "日程"), b_calendar),
        (has("域名", "IP查询", "whois"), b_whois),
        # 注意：放在 b_code 之后。含「仓库/分支/github」的查询优先走 GitHub 仓库检索，
        # 避免被「搜一下」等通用网页搜索词抢走路由（如「搜一下 ai-code 相关的仓库」）。
        (has("公开资料", "外网检索", "联网搜索", "新闻", "最新消息", "最新动态",
             "资讯", "热搜", "头条", "实时信息", "上网查", "网上查", "搜一下", "搜素", "搜索",
             "股价", "股票", "百科", "热点是", "热点新闻"), b_web),
        (has("现在几点", "当前时间", "现在时间", "几号", "时区", "现在几点了", "今天几号", "星期几", "今天是周"), b_time),
        (has("计算", "算一下", "数学", "等于多少"), b_math),
        (has("git 周报", "本周工作", "周报统计", "提交统计", "提交周报", "代码周报", "周报"), b_git_weekly),
        (has("向量", "语义检索", "相似文档", "语义搜索"), b_vector),
        (has("解释代码", "代码说明", "这段代码", "代码含义"), b_code_explain),
        (has("分析 bug", "排查", "定位缺陷", "报错原因", "故障"), b_bug),
    ]
    return rules


async def plan_query(query: str, available_names: set[str], ctx: ToolContext) -> dict:
    """Return a plan: {mode, parallel, steps:[...]}.

    `available_names` restricts to tools the user may actually use.

    性能与可用性保护（真实模型模式下尤为关键）：
      - 规则快通道：若关键词规则已明确命中（如时间/数学/天气等本地即可处理的
        轻量问题），直接秒回，避免每次都去打慢速的内网推理服务。
      - LLM 硬超时：真实模型规划失败时回退规则，保证数秒内必有响应。
    """
    # 1) 规则快通道：命中（含识别出意图但工具暂不可用）即返回，绝不走慢模型空转
    rule_plan = _plan_query_rules(query, available_names, ctx)
    if rule_plan["mode"] != "none" or rule_plan.get("matched_but_unavailable"):
        return rule_plan

    # 2) 真实模型规划（带硬超时，失败/超时回退规则兜底）
    if not settings_MOCK():
        try:
            return await asyncio.wait_for(
                plan_query_llm(query, available_names, ctx), timeout=15
            )
        except Exception:
            return rule_plan
    return rule_plan


async def plan_query_llm(query: str, available_names: set[str], ctx: ToolContext) -> dict:
    """Real-model planning via function calling (used when MOCK_LLM=false)."""
    from app.db.base import get_session
    from app.tools.registry import build_function_schemas
    from sqlalchemy import select

    from app.db.models import Tool

    tools = await _tools_for_ctx(ctx)
    schemas = build_function_schemas([t for t in tools if t.name in available_names])
    messages = [{"role": "user", "content": query}]
    resp = await chat(messages, tools=schemas, model=settings.LLM_REASONING_MODEL)
    if "tool_calls" in resp:
        steps = [{"tool": c["name"], "args": c["arguments"], "display": c["name"]} for c in resp["tool_calls"]]
        return {"mode": "single" if len(steps) == 1 else "multi", "parallel": False, "steps": steps, "answer": None}
    return {"mode": "none", "parallel": False, "steps": [], "answer": resp.get("content", "")}


async def plan_query_fallback(query, available_names, ctx):
    # 规则兜底：严禁回调 plan_query，否则会无限递归导致 RecursionError
    return _plan_query_rules(query, available_names, ctx)


def _plan_query_rules(query: str, available_names: set[str], ctx: ToolContext) -> dict:
    rules = _detectors()
    found = []
    matched_but_unavailable = set()  # 规则命中了工具，但当前用户无权限/工具未启用
    for matcher, builder in rules:
        if matcher(query):
            step = builder(query, ctx)
            if step:
                if step["tool"] in available_names:
                    found.append((query.find(step["tool"]), step))
                else:
                    matched_but_unavailable.add(step["tool"])

    # 知识库检索统一走 doc_search（内部已实现 RAG 优先 + 回退在线文档）：
    # 查询含「知识库」且已命中 doc_search 时，剔除 vector_search，避免两者重复触发
    if "知识库" in query and any(step["tool"] == "doc_search" for _, step in found):
        found = [(pos, step) for (pos, step) in found if step["tool"] != "vector_search"]

    # de-duplicate by tool, keep first appearance order (按在 query 中首次出现位置排序)
    seen = set()
    steps = []
    for _, step in sorted(found, key=lambda x: x[0]):
        if step["tool"] in seen:
            continue
        seen.add(step["tool"])
        steps.append(step)

    if not steps:
        if matched_but_unavailable:
            # 意图已识别，但对应工具当前角色无权使用或未启用/未注册，给出明确提示而非笼统的“未匹配”
            names = "、".join(sorted(matched_but_unavailable))
            return {
                "mode": "none",
                "parallel": False,
                "steps": [],
                "matched_but_unavailable": names,
                "answer": f"已识别你的意图需要调用工具：{names}，但该工具当前未启用或未注册。"
                          f"请重启后端以完成工具注册（已自动补齐），或由管理员在后台启用后重试。",
            }
        return {
            "mode": "none",
            "parallel": False,
            "steps": [],
            "answer": "抱歉，我暂未匹配到可调用的内部工具。你可以尝试：查客户、查考勤、发邮件、生成图表、查库存、查产品、生成报价单等。",
        }
    mode = "single" if len(steps) == 1 else "multi"
    return {"mode": mode, "parallel": False, "steps": steps, "answer": None}


async def _tools_for(session, ctx):
    from app.tools.registry import list_enabled_tools

    return await list_enabled_tools(session, _user_from_ctx(ctx))


async def _tools_for_ctx(ctx):
    from app.db.base import async_session_maker

    async with async_session_maker() as session:
        return await _tools_for(session, ctx)


def _user_from_ctx(ctx: ToolContext):
    # Build a minimal User-like object for RBAC filter
    from app.db.models import User

    u = User()
    u.role = ctx.role
    u.department = ctx.department
    return u


def settings_MOCK() -> bool:
    from app.config import settings

    return settings.MOCK_LLM
