"""外网检索工具（默认关闭，管理员按需开启，受 EXTERNAL_TOOLS_ENABLED 管控）.

天气/域名(IP) 使用免密钥公开 API（Open-Meteo / RDAP），配置 MOCK_TOOLS=false
且管理员开启外网开关后即可真实调用；日历/公开检索需在 .env 配置对应地址/密钥。
"""
from __future__ import annotations

import html
import logging
import re
import urllib.parse

from app.config import settings
from app.core.http import aget
from app.tools.base import ToolContext, ToolResult, fail, ok_text

logger = logging.getLogger(__name__)


async def weather_query(args: dict, ctx: ToolContext) -> ToolResult:
    city = args.get("city", "北京")
    if settings.MOCK_TOOLS:
        return ok_text(f"🌤️ {city} 今日天气：多云转晴，22~30°C，东南风 3 级，空气质量良。")
    try:
        geo = await aget("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "language": "zh", "count": 1})
        if not geo.get("results"):
            return fail(f"未找到城市：{city}")
        loc = geo["results"][0]
        cur = await aget("https://api.open-meteo.com/v1/forecast",
                         params={"latitude": loc["latitude"], "longitude": loc["longitude"],
                                 "current": "temperature_2m,weather_code,wind_speed_10m"})
        c = cur.get("current", {})
        return ok_text(f"🌤️ {city} 当前 {c.get('temperature_2m')}°C，风速 {c.get('wind_speed_10m')} km/h")
    except Exception as e:  # noqa: BLE001
        return fail(f"天气查询失败：{e}")


async def calendar_query(args: dict, ctx: ToolContext) -> ToolResult:
    date = args.get("date", "")
    # 真实接入 business-systems/biz 的 /calendar/events（与四个自研工具一致）；
    # MOCK_TOOLS=true 或未配置 BIZ_BASE_URL 时回退演示数据。
    if settings.MOCK_TOOLS or not settings.BIZ_BASE_URL:
        return ok_text("📅 今日日程（演示）：10:00 部门周会；14:30 客户演示；17:00 版本发布评审。")
    try:
        base = settings.BIZ_BASE_URL.rstrip("/")
        data = await aget(base + "/calendar/events", token=settings.BIZ_TOKEN,
                          params={"date": date}, headers={"X-Act-User": ctx.username or "",
                                                          "X-Act-Role": ctx.role or "employee"})
        events = (data.get("events") if isinstance(data, dict) else data) or []
        if not events:
            return ok_text(f"📅 {date or '今日'} 暂无日程安排。")
        lines = [f"📅 {date or '今日'} 日程（共 {len(events)} 项）："]
        for e in events:
            when = f"{e.get('start')}-{e.get('end')}" if e.get("end") else e.get("start", "")
            loc = f"　📍{e['location']}" if e.get("location") else ""
            att = f"　👥{e['attendees']}" if e.get("attendees") else ""
            lines.append(f"- {when} {e.get('title','')}{loc}{att}")
        return ok_text("\n".join(lines))
    except Exception as e:  # noqa: BLE001
        return fail(f"日历查询失败：{e}")


async def whois_query(args: dict, ctx: ToolContext) -> ToolResult:
    domain = args.get("domain", "")
    if settings.MOCK_TOOLS:
        return ok_text(f"🔎 {domain} 域名信息：注册商=示例注册局，注册时间=2020-01-01，到期=2027-01-01，DNS=ns1.corp.com。")
    try:
        # RDAP 免密钥；自动识别 IP / 域名
        import ipaddress
        try:
            ipaddress.ip_address(domain)
            url = f"https://rdap.org/ip/{domain}"
        except ValueError:
            url = f"https://rdap.org/domain/{domain}"
        data = await aget(url)
        return ok_text(f"🔎 {domain} RDAP：\n" + "\n".join(
            f"- {k}: {v}" for k, v in data.items() if k in ("ldhName", "handle", "status", "events")))
    except Exception as e:  # noqa: BLE001
        return fail(f"WHOIS 查询失败：{e}")


def _render_results(source: str, q: str, items: list[tuple[str, str, str]]) -> str:
    """统一渲染检索结果为易读的分条格式。items: [(title, url, snippet), ...]"""
    lines = [f"🔎 公开资料检索「{q}」", f"📡 来源：{source}　共 {len(items)} 条", ""]
    for i, (title, url, snippet) in enumerate(items, 1):
        lines.append(f"{i}. {title}")
        lines.append(f"   🔗 {url}")
        if snippet:
            lines.append(f"   📝 {snippet}")
        lines.append("")  # 条目间空行分隔，便于阅读
    return "\n".join(lines).rstrip()


def _parse_tavily(data: dict) -> list[tuple[str, str, str]]:
    """解析 Tavily Search 返回（结构化 JSON），返回 (标题, 链接, 摘要)。"""
    items: list[tuple[str, str, str]] = []
    answer = (data.get("answer") or "").strip()
    if answer:
        items.append(("💡 综合答案", "Tavily 聚合结果", answer))
    for r in data.get("results", [])[:5]:
        title = (r.get("title") or "").strip()
        url = r.get("url") or ""
        content = (r.get("content") or "").strip()
        if not url:
            continue
        items.append((title, url, content[:200]))
        if len(items) >= 6:
            break
    return items


async def _wiki_search(q: str) -> list[tuple[str, str, str]]:
    """维基百科官方 API（zh 优先，en 兜底），免密钥、稳定，返回 (标题, 链接, 摘要)。"""
    items: list[tuple[str, str, str]] = []
    for lang in ("zh", "en"):
        try:
            data = await aget(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": q,
                        "format": "json", "srlimit": 5, "srprop": "snippet"},
                headers={"User-Agent": "AI-Agent-Tool/1.0 (enterprise-agent)"},
                timeout=10,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("维基百科(%s)检索失败：%s", lang, e)
            continue
        if not isinstance(data, dict):
            continue
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", ""))).strip()
            if not title:
                continue
            url = "https://" + lang + ".wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
            items.append((title, url, snippet[:160]))
            if len(items) >= 5:
                break
        if items:
            return items
    return items


def _parse_bing(html: str) -> list[tuple[str, str, str]]:
    """从 Bing 搜索结果页（HTML）提取前几条结果，返回 (标题, 链接, 摘要)。"""
    items: list[tuple[str, str, str]] = []
    for blk in re.findall(r'<li class="b_algo".*?</li>', html, re.S):
        href = re.search(r'<a[^>]+href="(https?://[^"]+)"', blk)
        title = re.search(r'<h2[^>]*>(.*?)</h2>', blk, re.S)
        if not href or not title:
            continue
        t = re.sub(r'<[^>]+>', '', title.group(1)).strip()
        snip = re.search(r'<p[^>]*>(.*?)</p>', blk, re.S)
        s = re.sub(r'<[^>]+>', '', snip.group(1)).strip() if snip else ""
        if t:
            items.append((t, href.group(1), s))
        if len(items) >= 5:
            break
    return items


def _parse_baidu(html: str) -> list[tuple[str, str, str]]:
    """从百度搜索结果页（HTML）提取前几条结果，返回 (标题, 链接, 摘要)。"""
    items: list[tuple[str, str, str]] = []
    for m in re.finditer(
        r'<h3[^>]*class="t"[^>]*>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        html, re.S,
    ):
        url = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if title:
            items.append((title, url, ""))
        if len(items) >= 5:
            break
    return items


_WEB_STOPWORDS = [
    "公开资料", "外网检索", "联网搜索", "检索资料", "检索一下", "帮我检索", "检索",
    "搜索一下", "搜索", "查询一下", "查询", "查一下", "查资料", "查", "资料",
    "相关信息", "的信息", "关于", "帮我", "我想知道", "了解一下", "介绍", "简介",
    "是什么", "是怎么", "请问", "给我", "找", "看看", "有关", "的",
]


def _clean_query(q: str) -> str:
    """清洗用户查询：剥离『公开资料/检索/查询』等指令词与修饰词，保留实体主体。

    例：「狄仁杰 公开资料」->「狄仁杰」；「查一下特斯拉的股价」->「特斯拉股价」。
    """
    s = q
    for w in _WEB_STOPWORDS:
        s = s.replace(w, " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip("，。？?！!、,.;；：:　 ").strip()
    return s or q.strip()


# 单字/姓氏/汉字等泛概念页的后缀特征（标题仅以实体首字开头且为这类页面时判定无关）
_GENERIC_SUFFIX = re.compile(r"(姓|氏|（.*）|汉语|汉字|拼音|部首|笔画|是什么意思|的解释|的拼音|的意思|百科)$")


def _filter_relevant(items: list[tuple[str, str, str]], core: str) -> list[tuple[str, str, str]]:
    """实体相关性过滤 + 排序：强相关优先；丢弃标题仅以实体首字开头的单字/姓氏/汉字泛概念页。

    例：查询『狄仁杰』时，过滤掉『狄（汉语汉字）』『狄姓』，保留真正与狄仁杰相关的页面。
    仅当实体长度 >= 2 时启用过滤，避免对单字实体误杀。
    """
    core = core.strip()
    if len(core) < 2:
        return items
    scored: list[tuple[int, str, str, str]] = []
    for title, url, snippet in items:
        # 强相关：标题/摘要/链接含完整实体 -> 最高优先级
        if core in title or core in snippet or core in url:
            scored.append((0, title, url, snippet))
            continue
        # 单字/姓氏陷阱：标题以实体首字开头，但其余部分是泛概念标记（如『姓』『（汉语汉字）』）
        if title.startswith(core[0]) and title != core:
            suffix = title[len(core[0]):]
            if _GENERIC_SUFFIX.search(suffix) or suffix in ("姓", "氏"):
                continue  # 丢弃无关单字/姓氏/汉字解释页
        scored.append((1, title, url, snippet))
    scored.sort(key=lambda x: x[0])
    return [(t, u, s) for (_, t, u, s) in scored]


async def web_search(args: dict, ctx: ToolContext) -> ToolResult:
    raw = args.get("query", "")
    q = _clean_query(raw)  # 实体清洗：剥离『公开资料』等噪声，得到真正检索词（如『狄仁杰』）
    if settings.MOCK_TOOLS:
        return ok_text(f"🔎 公开资料检索「{q}」：返回 3 条结果（示例）。实际部署请接入合规检索服务。")

    # 1) Tavily Search（需 TAVILY_API_KEY，专为 LLM 优化的检索，质量最佳）
    if settings.tavily_api_key:
        try:
            data = await apost(
                "https://api.tavily.com/search",
                json={"api_key": settings.tavily_api_key, "query": q,
                      "search_depth": "basic", "max_results": 5, "include_answer": False},
                timeout=12,
            )
            if isinstance(data, dict):
                items = _filter_relevant(_parse_tavily(data), q)
                if items:
                    return ok_text(_render_results("Tavily Search", q, items))
        except Exception as e:  # noqa: BLE001
            logger.warning("Tavily 检索失败，转维基百科兜底：%s", e)

    # 2) 维基百科官方 API（免密钥，事实/百科类查询稳）
    try:
        items = _filter_relevant(await _wiki_search(q), q)
        if items:
            return ok_text(_render_results("维基百科", q, items))
    except Exception as e:  # noqa: BLE001
        logger.warning("维基百科检索失败：%s", e)

    # 3) 百度兜底（免密钥，国内网络最易访问）
    try:
        html_text = await aget("https://www.baidu.com/s", params={"wd": q},
                               headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                        "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=8)
        if isinstance(html_text, str):
            items = _filter_relevant(_parse_baidu(html_text), q)
            if items:
                return ok_text(_render_results("百度", q, items))
    except Exception as e:  # noqa: BLE001
        logger.warning("百度检索失败：%s", e)

    # 4) Bing 兜底（免密钥）
    try:
        html_text = await aget("https://www.bing.com/search", params={"q": q},
                               headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                               timeout=8)
        if isinstance(html_text, str):
            items = _filter_relevant(_parse_bing(html_text), q)
            if items:
                return ok_text(_render_results("Bing", q, items))
    except Exception as e:  # noqa: BLE001
        logger.warning("Bing 检索失败：%s", e)

    return fail(f"公开资料检索失败：针对「{q}」未能从 Tavily / 维基百科 / 百度 / Bing 获取相关结果"
                "（当前网络可能无法访问外网检索服务；如需稳定检索请配置 TAVILY_API_KEY 接入 Tavily Search）。")


ADAPTERS = {
    "weather_query": weather_query,
    "calendar_query": calendar_query,
    "whois_query": whois_query,
    "web_search": web_search,
}
