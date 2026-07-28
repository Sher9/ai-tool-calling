"""Git 周报生成工具（基于 GitHub）.

读取 GitHub 上某个仓库（owner/name）的提交记录，汇总生成结构化周报：
- 支持按作者、时间范围、分支过滤
- 自动按提交类型（feat/fix/docs/refactor 等）分类
- 输出 Markdown 周报 + 可选表格统计

通过 GitHub REST API（/repos/{owner}/{repo}/commits）拉取，配置
GITHUB_BASE_URL + GITHUB_TOKEN 后真实查询；未配置则演示。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from app.config import settings
from app.core.http import aget
from app.tools.base import ToolContext, ToolResult, fail, ok_table, ok_text

# 提交类型前缀 -> 中文分类
_CONV_PREFIX = {
    "feat": "新功能",
    "fix": "缺陷修复",
    "docs": "文档",
    "style": "格式调整",
    "refactor": "重构",
    "perf": "性能优化",
    "test": "测试",
    "build": "构建/依赖",
    "ci": "CI/CD",
    "chore": "杂项",
    "revert": "回滚",
}

_CONV_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<break>!)?:\s*(?P<msg>.*)", re.DOTALL)


def _resolve_range(since: str | None, until: str | None) -> tuple[str, str]:
    """归一化时间范围为 GitHub 需要的 ISO 8601 时间；默认最近 7 天。"""
    if until:
        until_dt = until
    else:
        until_dt = date.today().isoformat()
    if since:
        since_dt = since
    else:
        d = datetime.strptime(until_dt, "%Y-%m-%d").date() - timedelta(days=6)
        since_dt = d.isoformat()
    return since_dt + "T00:00:00Z", until_dt + "T23:59:59Z"


def _classify(subject: str) -> tuple[str, str]:
    """解析 conventional-commit 前缀，返回 (分类, 摘要)。"""
    m = _CONV_RE.match(subject.strip())
    if m:
        t = m.group("type").lower()
        scope = m.group("scope")
        label = _CONV_PREFIX.get(t, t)
        summary = m.group("msg").strip()
        if scope:
            summary = f"({scope}) {summary}"
        return label, summary
    return "其他", subject.strip()


def _build_markdown(repo_name: str, author: str, since: str, until: str,
                    commits: list[dict]) -> str:
    lines = [
        f"# 工作周报（{since} ~ {until}）",
        "",
        f"- 仓库：`{repo_name}`",
        f"- 作者：{author or '全部'}",
        f"- 提交总数：**{len(commits)}**",
        "",
        "## 一、按类型汇总",
    ]
    by_type = defaultdict(list)
    for c in commits:
        by_type[c["category"]].append(c)
    for cat in sorted(by_type, key=lambda k: -len(by_type[k])):
        lines.append(f"- {cat}：{len(by_type[cat])} 次")
    lines.append("")
    lines.append("## 二、提交明细")
    for cat in sorted(by_type, key=lambda k: -len(by_type[k])):
        lines.append(f"### {cat}")
        for c in by_type[cat]:
            lines.append(f"- {c['date']} · {c['summary']}  `{c['short']}`")
        lines.append("")
    if not commits:
        lines.append("_该时间范围内无提交记录。_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def git_weekly_report(args: dict, ctx: ToolContext) -> ToolResult:
    """读取 GitHub 某仓库的提交记录并生成 Markdown 周报。"""
    repo = (args.get("repo") or "").strip()  # 形如 owner/name
    if not repo or "/" not in repo:
        return fail("请提供 GitHub 仓库名（owner/name），例如 repo=octocat/Hello-World")

    author = (args.get("author") or "").strip()
    branch = (args.get("branch") or "").strip()
    since, until = _resolve_range(args.get("since"), args.get("until"))

    if settings.MOCK_TOOLS or not settings.GITHUB_TOKEN:
        # 演示数据：使用传入的 repo / author，避免硬编码 octocat 造成的
        # "仓库名是 Sher9/ai-call、作者却是 octocat" 这种明显不对的周报。
        demo_author = author or "you"
        demo = [
            ("a1b2c3d", "2026-07-22", demo_author, "feat: 新增 GitHub 周报生成"),
            ("e4f5g6h", "2026-07-23", demo_author, "fix: 修正分支过滤逻辑"),
            ("i7j8k9l", "2026-07-25", demo_author, "docs: 补充 README 示例"),
        ]
        commits = [{"short": s, "date": d, "author": w, **dict(zip(["category", "summary"], _classify(m)))}
                   for s, d, w, m in demo]
        md = _build_markdown(repo, author, since[:10], until[:10], commits)
        text = (
            md + "\n## 三、类型统计\n" + _table_to_text(["类型", "次数"], [["新功能", "1"], ["缺陷修复", "1"], ["文档", "1"]])
            + "\n\n⚠️ 当前为演示模式（MOCK_TOOLS=true 或未配置 GITHUB_TOKEN），以上提交为固定占位、"
            "并非该仓库真实记录。\n接入真实数据：在 .env 中填写 GITHUB_TOKEN（repo 读权限）并设 MOCK_TOOLS=false。"
        )
        return ok_text(text)

    gh = settings.GITHUB_BASE_URL.rstrip("/")
    headers = {"Accept": "application/vnd.github+json"}
    params = {"since": since, "until": until, "per_page": 100}
    if author:
        params["author"] = author
    if branch:
        params["sha"] = branch

    try:
        data = await aget(f"{gh}/repos/{repo}/commits", token=settings.GITHUB_TOKEN,
                          headers=headers, params=params)
    except Exception as e:  # noqa: BLE001
        return fail(f"GitHub 提交记录获取失败：{e}")

    items = data if isinstance(data, list) else []
    commits: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        c = it.get("commit", {})
        who = (it.get("author") or {}).get("login") or (c.get("author") or {}).get("name", "")
        day = (c.get("author") or {}).get("date", "")[:10]
        subject = (c.get("message") or "").splitlines()[0]
        category, summary = _classify(subject)
        commits.append({"short": (it.get("sha") or "")[:7], "date": day,
                        "author": who, "category": category, "summary": summary})

    commits.sort(key=lambda c: (c["date"], c["short"]), reverse=True)

    md = _build_markdown(repo, author, since[:10], until[:10], commits)
    counter = Counter(c["category"] for c in commits)
    rows = [[cat, str(n)] for cat, n in counter.most_common()] or [["（无）", "0"]]
    text = md + "\n## 三、类型统计\n" + _table_to_text(["类型", "次数"], rows)
    return ok_text(text)


def _table_to_text(columns: list[str], rows: list[list]) -> str:
    head = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)
    return f"{head}\n{sep}\n{body}"


ADAPTERS = {
    "git_weekly_report": git_weekly_report,
}
