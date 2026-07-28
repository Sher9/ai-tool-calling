"""工具执行器 (层级 3.5).

Loads the Tool rows for a plan, runs each step through the registry with retry /
circuit-breaker semantics, and formats the aggregated answer. Supports serial or
parallel step execution.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from sqlalchemy import select

from app.db.models import Tool
from app.tools.base import ToolContext, ToolResult, fail
from app.tools.registry import dispatch

StepEvent = Callable[[str, dict], Awaitable[None]]


async def _load_tools(session, names: list[str]) -> dict[str, Tool]:
    stmt = select(Tool).where(Tool.name.in_(names))
    res = await session.execute(stmt)
    return {t.name: t for t in res.scalars().all()}


async def _run_one(tool: Tool | None, step: dict, ctx: ToolContext, session) -> dict:
    if tool is None:
        r = fail(f"工具「{step['tool']}」不存在或未授权")
    else:
        r = await _run_with_retry(tool, step, ctx, session)
    return {
        "tool": step["tool"],
        "display_name": (tool.display_name if tool else step["tool"]),
        "display": step.get("display", step["tool"]),
        "args": step.get("args", {}),
        "status": "success" if r.ok else "failed",
        "result": r.to_payload(),
        "error": r.error,
    }


async def _run_with_retry(tool: Tool, step: dict, ctx: ToolContext, session) -> ToolResult:
    last: ToolResult | None = None
    for attempt in range(2):  # 1 retry
        try:
            last = await dispatch(tool, step.get("args", {}), ctx, session)
            if last.ok or attempt == 1:
                return last
        except Exception as e:  # noqa: BLE001
            last = fail(f"执行异常：{e}")
    return last or fail("未知错误")


def _result_summary(entry: dict) -> str:
    res = entry["result"]
    if not res["ok"]:
        return f"❌ {entry['display']} 失败：{res.get('error')}"
    if res["kind"] == "table":
        rows = res["table"].get("rows", [])
        return f"✅ {entry['display']}：返回 {len(rows)} 条记录。"
    if res["kind"] == "chart":
        return f"✅ {entry['display']}：已生成图表。"
    if res["kind"] == "file":
        return f"✅ {entry['display']}：已生成文件 {res['file'].get('name')}。"
    return f"✅ {entry['display']}：{res['text'][:200]}"


async def run_plan(plan: dict, ctx: ToolContext, session, emit: StepEvent | None = None) -> tuple[list[dict], str]:
    steps = plan.get("steps", [])
    tools = await _load_tools(session, [s["tool"] for s in steps])

    results: list[dict] = []

    async def _one(step: dict) -> dict:
        if emit:
            await emit("step_start", {"tool": step["tool"], "display": step.get("display", step["tool"])})
        entry = await _run_one(tools.get(step["tool"]), step, ctx, session)
        if emit:
            await emit("step_result", entry)
        return entry

    if plan.get("parallel"):
        results = await _gather(_one, steps)
    else:
        for step in steps:
            results.append(await _one(step))

    answer = _compose(plan, results)
    return results, answer


async def _gather(fn, steps):
    import asyncio

    return await asyncio.gather(*[fn(s) for s in steps])


def _compose(plan: dict, results: list[dict]) -> str:
    if plan.get("mode") == "none":
        return plan.get("answer") or "已完成。"
    # 单步文本结果：直接返回工具格式化后的全文（流式时步骤面板已展示检索过程，
    # 此处避免再叠加一份，造成结果重复）。
    if len(results) == 1 and results[0]["result"]["ok"] and results[0]["result"]["kind"] == "text":
        return results[0]["result"]["text"]
    lines = [f"已为你完成 {len(results)} 项任务："]
    for i, entry in enumerate(results, 1):
        lines.append(f"{i}. {_result_summary(entry)}")
    return "\n".join(lines)


async def stream_plan(plan: dict, ctx: ToolContext, session):
    """Async generator yielding per-step events for SSE streaming.

    Emits: {"kind": "step_start", ...}, {"kind": "step_result", "entry": ...},
           {"kind": "done", "answer": ..., "results": [...]}
    """
    steps = plan.get("steps", [])
    tools = await _load_tools(session, [s["tool"] for s in steps])
    results: list[dict] = []
    for step in steps:
        yield {"kind": "step_start", "tool": step["tool"], "display": step.get("display", step["tool"])}
        entry = await _run_one(tools.get(step["tool"]), step, ctx, session)
        results.append(entry)
        yield {"kind": "step_result", "entry": entry}
    yield {"kind": "done", "answer": _compose(plan, results), "results": results}
