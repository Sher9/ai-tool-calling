"""LangGraph state graph (层级 3.3 编排).

Nodes: plan (Planner) -> retrieve (RAG, 条件跳过) -> execute (Executor) -> summarize.
This compiled graph powers the canonical (non-streaming) chat path and shows the
LangGraph integration; the streaming chat endpoint reuses the same node logic.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agent import executor as executor_mod
from app.agent import planner as planner_mod
from app.agent import rag as rag_mod
from app.db.models import User
from app.tools.base import ToolContext

# 纯本地/无需知识库的轻量工具：命中这些工具时跳过 RAG 检索，避免无意义的 10s+ 延迟
LOCAL_TOOLS = {
    "get_current_time", "math_calculate",
    "code_explain", "bug_analyze",
}


class AgentState(TypedDict):
    query: str
    ctx: ToolContext
    session: Any
    rag: list
    used_rag: bool
    rag_sources: list
    plan: dict
    results: list
    answer: str


def _user(ctx: ToolContext) -> User:
    u = User()
    u.role = ctx.role
    u.department = ctx.department
    return u


async def plan_node(state: AgentState) -> dict:
    from app.tools.registry import list_enabled_tools

    tools = await list_enabled_tools(state["session"], _user(state["ctx"]))
    available = {t.name for t in tools}
    plan = await planner_mod.plan_query(state["query"], available, state["ctx"])
    return {"plan": plan}


async def retrieve_node(state: AgentState) -> dict:
    # 纯本地工具问题无需知识库检索：跳过 RAG，显著降延迟（如"当前时区"）。
    steps = state.get("plan", {}).get("steps", [])
    need_rag = bool(steps) and not all(s["tool"] in LOCAL_TOOLS for s in steps)
    if not need_rag:
        return {"rag": [], "used_rag": False, "rag_sources": []}
    chunks = await rag_mod.retrieve(
        state["session"], state["query"], state["ctx"].department,
        user_id=state["ctx"].user_id, include_episodic=True,
    )
    return {
        "rag": chunks,
        "used_rag": bool(chunks),
        "rag_sources": [c["title"] for c in chunks],
    }


async def execute_node(state: AgentState) -> dict:
    results, answer = await executor_mod.run_plan(state["plan"], state["ctx"], state["session"])
    return {"results": results, "answer": answer}


async def summarize_node(state: AgentState) -> dict:
    answer = state.get("answer", "")
    if state.get("rag"):
        top = state["rag"][0]
        ref = top.get("source") or top.get("title") or "知识库"
        sec = top.get("section")
        cite = f"《{ref}》" + (f" / {sec}" if sec else "")
        excerpt = top["content"][:300]
        answer += f"\n\n📚 参考知识库{cite}：\n{excerpt}"
    return {"answer": answer}


def build_graph():
    # 注意：node 名不能与 AgentState 的字段名冲突（如 "plan" 已是 state key），
    # 因此节点用 "planner"/"retriever"/"executor"/"summarizer" 命名。
    g = StateGraph(AgentState)
    g.add_node("planner", plan_node)
    g.add_node("retriever", retrieve_node)
    g.add_node("executor", execute_node)
    g.add_node("summarizer", summarize_node)
    g.set_entry_point("planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "executor")
    g.add_edge("executor", "summarizer")
    g.add_edge("summarizer", END)
    return g.compile()


async def run_agent(query: str, ctx: ToolContext, session) -> dict:
    """Run the full agent pipeline (non-streaming). Returns final state dict."""
    graph = build_graph()
    state: AgentState = {
        "query": query,
        "ctx": ctx,
        "session": session,
        "rag": [],
        "used_rag": False,
        "rag_sources": [],
        "plan": {},
        "results": [],
        "answer": "",
    }
    result = await graph.ainvoke(state)
    return result
