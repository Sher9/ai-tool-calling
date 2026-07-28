"""Chat endpoint: natural-language task orchestration (层级 1 交互入口).

Supports two modes:
  - POST /chat          : full JSON response (non-streaming, via LangGraph)
  - POST /chat/stream   : Server-Sent-Events with live plan + step visualization
"""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import executor as executor_mod
from app.agent import planner as planner_mod
from app.agent import rag as rag_mod
from app.agent.episodic import summarize_conversation
from app.agent.graph import run_agent
from app.agent.memory import append_message, record_preference
from app.api.deps import client_ip, get_session
from app.core.audit import write_audit
from app.core.security import get_current_user
from app.db.base import async_session_maker
from app.db.models import Conversation, Message, TaskRecord, User
from app.schemas.chat import ChatRequest, ChatResponse, ChatStep, ConversationOut
from app.tools.base import ToolContext
from app.tools.registry import list_enabled_tools

router = APIRouter(prefix="/chat", tags=["chat"])

SENSITIVE_TOOLS = {"crm_query", "hr_query", "finance_query", "email_query"}

# 仅当计划命中「知识检索类工具」时才调用 RAG（embedding + 向量召回，单步可达 10s+）。
# 业务工具（库存/客户/报价/邮件/服务器等）不依赖知识库上下文，跳过 RAG 可显著降延迟。
RAG_TOOLS = {"vector_search", "doc_search"}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _normalize_conv_id(conv_id) -> str | None:
    """把常见假值（None / "" / "null" / "undefined"）归一成 None，
    让调用方始终按“需要新建会话”处理，避免脏字符串写入外键导致冲突。"""
    if conv_id is None:
        return None
    if isinstance(conv_id, str) and conv_id.strip().lower() in ("", "null", "none", "undefined"):
        return None
    return conv_id


async def _resolve_conversation(session, user, conv_id, first_msg) -> Conversation:
    conv_id = _normalize_conv_id(conv_id)
    if conv_id:
        conv = await session.get(Conversation, conv_id)
        if conv and conv.user_id == user.id:
            return conv
    conv = Conversation(user_id=user.id, title=first_msg[:30])
    session.add(conv)
    await session.flush()
    await session.refresh(conv)
    return conv


async def _add_message(session, conv_id, role, content, meta=None) -> None:
    session.add(Message(conversation_id=conv_id, role=role, content=content, meta=meta or {}))


async def safe_summarize(user_id, department, messages) -> None:
    """后台安全地做情节记忆抽取；使用独立会话，绝不依赖可能已关闭的请求会话。
    任何异常吞掉，绝不抛到事件循环。"""
    try:
        async with async_session_maker() as session:
            await summarize_conversation(session, user_id, department, messages)
    except Exception:
        pass


async def safe_persist_turn(user, conversation, query, answer, results, used_rag, sources, ip, charts=None) -> None:
    """后台安全地持久化本轮对话；使用独立会话，绝不依赖可能已关闭的请求会话。
    任何异常吞掉并打印，绝不抛到事件循环，也不阻塞前端收尾。"""
    try:
        async with async_session_maker() as session:
            await _persist_turn(session, user, conversation, query, answer, results,
                                used_rag, sources, ip, charts=charts)
    except Exception:
        import traceback as _tb
        print("[chat_stream] persist_turn error:", _tb.format_exc(), flush=True)


async def _persist_turn(session, user, conversation, query, answer, results, used_rag, sources, ip, charts=None) -> None:
    await _add_message(session, conversation.id, "user", query)
    await _add_message(session, conversation.id, "assistant", answer,
                       meta={"steps": results, "rag": sources, "charts": charts or []})
    await append_message(conversation.id, "user", query)
    await append_message(conversation.id, "assistant", answer)
    await record_preference(user.id, query)

    for r in results:
        sensitive = r["tool"] in SENSITIVE_TOOLS and r["status"] == "success"
        await write_audit(
            session, user_id=user.id, username=user.username, action="tool_call",
            resource=r["tool"], detail={"args": r["args"], "status": r["status"]},
            ip=ip, sensitive=sensitive, commit=False,
        )
    session.add(TaskRecord(
        conversation_id=conversation.id, user_id=user.id, title=query[:50],
        plan={"steps": results}, status="success" if all(x["status"] == "success" for x in results) else "partial",
    ))
    await session.commit()


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    request: Request = None,
):
    ip = client_ip(request) if request else "unknown"
    conversation = await _resolve_conversation(session, user, req.conversation_id, req.message)
    ctx = ToolContext(user_id=user.id, username=user.username, role=user.role, department=user.department, ip=ip)
    state = await run_agent(req.message, ctx, session)
    results = state["results"]
    await _persist_turn(session, user, conversation, req.message, state["answer"], results,
                        state["used_rag"], state["rag_sources"], ip)
    # 长期情节记忆：对话结束抽取关键事实入库（后台异步，不阻塞响应）
    asyncio.create_task(safe_summarize(
        user.id, user.department,
        [{"role": "user", "content": req.message}, {"role": "assistant", "content": state["answer"]}],
    ))
    return ChatResponse(
        conversation_id=conversation.id,
        answer=state["answer"],
        steps=[ChatStep(**_to_step(r)) for r in results],
        used_rag=state["used_rag"],
        rag_sources=state["rag_sources"],
    )


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    request: Request = None,
):
    ip = client_ip(request) if request else "unknown"
    ctx = ToolContext(user_id=user.id, username=user.username, role=user.role, department=user.department, ip=ip)

    async def event_gen():
        try:
            # 流式响应在 yield 期间会挂起，依赖注入的会话可能被提前回收/处于异常状态，
            # 因此生成器内自行持有独立会话，生命周期完全自控，避免 commit 卡死。
            async with async_session_maker() as session:
                conversation = await _resolve_conversation(session, user, req.conversation_id, req.message)
                tools = await list_enabled_tools(session, user)
                available = {t.name for t in tools}

                plan = await planner_mod.plan_query(req.message, available, ctx)
                yield sse("plan", {"mode": plan["mode"], "steps": [s.get("display", s["tool"]) for s in plan["steps"]]})

                # 仅知识检索类工具需要 RAG；业务工具问题跳过，显著降延迟
                need_rag = any(s["tool"] in RAG_TOOLS for s in plan["steps"])
                if need_rag:
                    chunks = await rag_mod.retrieve(session, req.message, user.department,
                                                    user_id=user.id, include_episodic=True)
                else:
                    chunks = []
                yield sse("rag", {"used": bool(chunks), "sources": [c["title"] for c in chunks]})

                results = []
                async for ev in executor_mod.stream_plan(plan, ctx, session):
                    if ev["kind"] == "step_start":
                        yield sse("step_start", {"tool": ev["tool"], "display": ev["display"]})
                    elif ev["kind"] == "step_result":
                        results.append(ev["entry"])
                        yield sse("step_result", ev["entry"])
                    elif ev["kind"] == "done":
                        answer = ev["answer"]
                        yield sse("answer", {"answer": answer})
                        # 把步骤中的图表结果（mermaid/图片）一并下发，供前端在回答中渲染
                        charts = [r["result"].get("chart") for r in results
                                  if r.get("result", {}).get("kind") == "chart" and r["result"].get("chart")]
                        if charts:
                            yield sse("charts", {"charts": charts})
                        # 持久化（写消息/审计/任务记录）改为后台异步，使用独立会话，不阻塞前端收尾
                        asyncio.create_task(safe_persist_turn(
                            user, conversation, req.message, answer, results,
                            bool(chunks), [c["title"] for c in chunks], ip, charts=charts))
                        # 记忆抽取（可能调慢速 LLM/embedding）改为后台异步，使用独立会话，不阻塞前端收尾
                        asyncio.create_task(safe_summarize(
                            user.id, user.department,
                            [{"role": "user", "content": req.message}, {"role": "assistant", "content": answer}],
                        ))
                        yield sse("done", {"conversation_id": conversation.id})
        except Exception as e:
            import traceback as _tb
            print("[chat_stream] event_gen error:", _tb.format_exc(), flush=True)
            yield sse("error", {"message": str(e)})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _to_step(r: dict) -> dict:
    return {
        "tool": r["tool"],
        "display_name": r.get("display_name") or r["tool"],
        "args": r.get("args", {}),
        "status": r["status"],
        "result": r["result"],
        "error": r.get("error"),
    }


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())
    )
    convs = res.scalars().all()
    return [ConversationOut(id=c.id, title=c.title, created_at=c.created_at.isoformat(), updated_at=c.updated_at.isoformat())
            for c in convs]


@router.get("/conversations/{conv_id}/messages")
async def conversation_messages(conv_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    conv = await session.get(Conversation, conv_id)
    if not conv or conv.user_id != user.id:
        return []
    res = await session.execute(select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at))
    msgs = res.scalars().all()
    return [{"id": m.id, "role": m.role, "content": m.content, "meta": m.meta, "created_at": m.created_at.isoformat()}
            for m in msgs]


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    conv = await session.get(Conversation, conv_id)
    if conv and conv.user_id == user.id:
        await session.delete(conv)
        await session.commit()
    return {"ok": True}
