"""研发技术工具（技术部专属）: GitHub 代码仓库 / 接口文档.

真实接入：配置 GITHUB_BASE_URL + GITHUB_TOKEN（PAT，repo 读权限），并将
MOCK_TOOLS=false 后发起真实 GitHub REST 调用；未配置则明确报错。
"""
from __future__ import annotations

import json

from app.config import settings
from app.core.http import aget
from app.tools.base import ToolContext, ToolResult, fail, ok_table, ok_text


async def github_search_repo(args: dict, ctx: ToolContext) -> ToolResult:
    """GitHub 代码仓库检索：
    - 传入 keyword：按关键词搜索仓库，返回仓库基础信息（名称/描述/语言/Star/默认分支等）
    - 传入 repo（owner/name）：列出该仓库的「所有分支」
    """
    keyword = (args.get("keyword") or "").strip()
    repo = (args.get("repo") or "").strip()  # 形如 owner/name

    if settings.MOCK_TOOLS or not settings.GITHUB_TOKEN:
        # 未接入真实 GitHub（MOCK_TOOLS=true 或缺少 GITHUB_TOKEN）时，不再返回
        # 与传入仓库无关的写死分支；而是基于传入的 repo 给出"演示分支"占位，并明确提示
        # 如何切换到真实查询，避免用户误以为这是真实仓库数据。
        if repo:
            branches = ["main", "develop", "release/1.0", "feature/login"]
            return ok_text(
                f"📦 仓库 `{repo}` 共 {len(branches)} 个分支（演示数据）：\n"
                + "\n".join(f"- {b}" for b in branches)
                + "\n\n⚠️ 当前为演示模式（MOCK_TOOLS=true 或未配置 GITHUB_TOKEN），"
                "以上分支为固定占位、并非该仓库真实分支。\n"
                "接入真实数据：在 .env 中填写 GITHUB_TOKEN（repo 读权限）并设 MOCK_TOOLS=false。"
            )
        rows = [
            ["octocat/Hello-World", "示例仓库", "Python", "1234", "main", "https://github.com/octocat/Hello-World"],
            ["octocat/Spoon-Knife", "练习 fork 用", "HTML", "567", "main", "https://github.com/octocat/Spoon-Knife"],
        ]
        rows = [r for r in rows if not keyword or keyword.lower() in (r[0] + r[1]).lower()]
        return ok_table(["仓库", "描述", "语言", "Star", "默认分支", "GitHub 地址"], rows) if rows else ok_text("未检索到相关仓库。")

    gh = settings.GITHUB_BASE_URL.rstrip("/")
    headers = {"Accept": "application/vnd.github+json"}
    try:
        if repo:
            # 仓库基础信息
            info = await aget(f"{gh}/repos/{repo}", token=settings.GITHUB_TOKEN, headers=headers)
            # 所有分支（分页拉满）
            branches = []
            page = 1
            while True:
                data = await aget(f"{gh}/repos/{repo}/branches", token=settings.GITHUB_TOKEN,
                                   headers=headers, params={"per_page": 100, "page": page})
                if not isinstance(data, list) or not data:
                    break
                branches.extend(d.get("name", "") for d in data if isinstance(d, dict))
                if len(data) < 100:
                    break
                page += 1
            basic = (f"📦 {info.get('full_name', repo)}\n"
                     f"描述：{info.get('description') or '（无）'}\n"
                     f"语言：{info.get('language') or '未知'}　Star：{info.get('stargazers_count', 0)}"
                     f"　默认分支：{info.get('default_branch', 'main')}")
            return ok_text(basic + f"\n\n🌿 共 {len(branches)} 个分支：\n" + "\n".join(f"- {b}" for b in branches))
        # 按关键词搜索仓库
        data = await aget(f"{gh}/search/repositories", token=settings.GITHUB_TOKEN,
                          headers=headers, params={"q": keyword, "per_page": 10})
        items = data.get("items", []) if isinstance(data, dict) else (data or [])
        rows = [[it.get("full_name", ""), (it.get("description") or "")[:40],
                 it.get("language") or "", it.get("stargazers_count", 0),
                 it.get("default_branch", "main"),
                 it.get("html_url") or ""]
                for it in items if isinstance(it, dict)]
        return ok_table(["仓库", "描述", "语言", "Star", "默认分支", "GitHub 地址"], rows) if rows else ok_text("未检索到相关仓库。")
    except Exception as e:  # noqa: BLE001
        return fail(f"GitHub 仓库检索失败：{e}")


def _parse_spec(raw: object) -> dict | None:
    """把 aget 返回的响应解析成 OpenAPI dict。

    aget 在响应不是 JSON 时会返回原始字符串（HTML 页面或 YAML 文档），
    这里依次尝试 JSON、YAML，并对 HTML（Swagger UI 页面）返回 None 以便给出明确提示。
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    # 1) 尝试 JSON
    try:
        return json.loads(text)
    except ValueError:
        pass
    # 2) 看起来是 HTML（Swagger UI 页面而非 OpenAPI 文档）
    head = text[:500].lower()
    if "<html" in head or "<!doctype" in head:
        return None
    # 3) 尝试 YAML
    try:
        import yaml  # PyYAML 为可选依赖
        return yaml.safe_load(text)
    except Exception:  # noqa: BLE001
        return None


async def swagger_parse(args: dict, ctx: ToolContext) -> ToolResult:
    path = (args.get("path") or "/api/v1/users").strip()
    method = (args.get("method") or "GET").upper()
    if settings.MOCK_TOOLS or not settings.SWAGGER_BASE_URL:
        example = (
            f"{method} {path} HTTP/1.1\n"
            f"Authorization: Bearer <token>\n"
            f"Content-Type: application/json\n\n"
            f'{{"page": 1, "size": 20}}'
        )
        return ok_text(f"【接口调用示例】\n```http\n{example}\n```")
    try:
        base = settings.SWAGGER_BASE_URL.rstrip("/")
        raw = await aget(base)
        spec = _parse_spec(raw)
        # 若配置的是 Swagger UI 的 HTML 页面（如 FastAPI 的 /docs、Swagger 的
        # /swagger-ui.html），自动回退到对应的 OpenAPI JSON 地址再尝试解析。
        if not isinstance(spec, dict):
            candidates: list[str] = []
            if base.lower().endswith("/docs"):
                candidates.append(base[: -len("/docs")].rstrip("/") + "/openapi.json")
            candidates += [
                base + "/openapi.json",
                base + "/api/v1/openapi.json",
                base + "/openapi.yaml",
                base + "/swagger/v1/swagger.json",
                base + "/v3/api-docs",
                base + "/v2/api-docs",
            ]
            for cand in candidates:
                try:
                    cand_raw = await aget(cand)
                except Exception:  # noqa: BLE001
                    continue
                cand_spec = _parse_spec(cand_raw)
                if isinstance(cand_spec, dict):
                    spec = cand_spec
                    break
        if not isinstance(spec, dict):
            return fail(
                "Swagger 解析失败：返回内容不是合法的 OpenAPI JSON/YAML 文档。"
                "FastAPI 的 Swagger UI（/docs）是 HTML 页面，不能直接解析；请改为指向其 OpenAPI "
                "JSON 地址，例如 http://127.0.0.1:8000/openapi.json（Springdoc 为 /v3/api-docs，"
                "Swagger 为 /v2/api-docs 或 *.json）。"
            )
        paths = spec.get("paths") or {}
        item = paths.get(path)
        if isinstance(item, str):  # 路径以外部 $ref 形式引用
            return fail(f"Swagger 中 {method} {path} 仅以 $ref 引用、未内联展开，无法解析。")
        if item is None:
            avail = list(paths.keys())[:20]
            return ok_text(
                f"✅ 已成功解析 OpenAPI 文档，但其中没有路径 `{path}`。\n"
                f"文档内可用的接口路径（前 20 个）：\n" + "\n".join(f"- {p}" for p in avail)
            )
        item = item or {}
        op = item.get(method.lower()) or item.get(method)
        if not isinstance(op, dict):
            return fail(f"Swagger 中未找到 {method} {path}")
        summary = op.get("summary", "")
        params = op.get("parameters", []) or []
        req_body = (
            op.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        ) or {}
        example = (
            f"# {summary}\n{method} {path}\n"
            f"参数：{', '.join(p.get('name', '') for p in params if isinstance(p, dict)) or '无'}\n"
            f"请求体 schema：{req_body or '无'}"
        )
        return ok_text(f"【接口文档解析】\n```\n{example}\n```")
    except Exception as e:  # noqa: BLE001
        return fail(f"Swagger 解析失败：{e}")


ADAPTERS = {
    "github_search_repo": github_search_repo,
    "swagger_parse": swagger_parse,
}
