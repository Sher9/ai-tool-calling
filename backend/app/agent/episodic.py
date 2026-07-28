"""长期情节记忆（Agent 记忆机制 · 层级 3）：跨会话沉淀用户偏好与历史关键事实。

- 写入：每次对话结束后由 LLM 抽取关键事实（如“用户 3 月咨询过公积金提取流程”）向量化入库。
- 召回：下次对话时按语义召回相关历史，作为个性化上下文注入 Prompt。
- 存储：pg_vector（EpisodicMemory 表），与语义记忆（RAG 知识库）共同构成长期记忆。
"""
from __future__ import annotations

import asyncio

from app.agent.rag import embed_text
from app.config import settings
from app.db.models import EpisodicMemory


async def store_episode(session, user_id: str, department: str, content: str, category: str = "fact") -> None:
    """将一条关键事实向量化后存入情节记忆。

    embed_text 调用 embedding 服务可能较慢/超时，用 12s 硬超时保护，
    避免记忆入库阻塞主响应链路。
    """
    content = (content or "").strip()
    if not content:
        return
    try:
        emb = await asyncio.wait_for(embed_text(content), timeout=12)
    except Exception:
        return
    session.add(EpisodicMemory(
        user_id=user_id,
        department=department,
        content=content,
        category=category,
        embedding=emb,
    ))
    await session.commit()


async def retrieve_episodes(session, query: str, user_id: str, department: str, limit: int = 3) -> list[str]:
    """按语义召回与当前查询相关的历史关键事实。"""
    if settings.MOCK_LLM:
        return []
    vec = await embed_text(query)
    from pgvector.sqlalchemy import cosine_distance
    from sqlalchemy import select

    stmt = (
        select(EpisodicMemory, cosine_distance(EpisodicMemory.embedding, vec).label("dist"))
        .where(EpisodicMemory.user_id == user_id)
        .order_by("dist")
        .limit(limit)
    )
    res = await session.execute(stmt)
    return [row[0].content for row in res.all()]


async def summarize_conversation(session, user_id: str, department: str, messages: list[dict]) -> str | None:
    """对话结束时抽取关键事实；返回文本并入库。无实质内容则返回 None。

    MOCK 模式：基于用户提问做轻量摘要（不调用大模型）。
    生产模式：调用大模型抽取结构化事实。
    """
    user_turns = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
    if not user_turns:
        return None

    if settings.MOCK_LLM:
        fact = "用户近期关注：" + "；".join(t[:60] for t in user_turns[-5:])
    else:
        from app.agent.llm import chat

        sys_prompt = (
            "你是记忆抽取器。请从下面的对话中抽取用户的关键事实、偏好与待办，"
            "每条一行，简洁客观，不要编造。若无实质信息，只回复空字符串。"
        )
        try:
            # 12s 硬超时：记忆抽取失败不应拖垮主响应链路（前端会一直转圈）
            resp = await asyncio.wait_for(
                chat(
                    [{"role": "system", "content": sys_prompt}] + messages,
                    model=settings.LLM_LIGHT_MODEL,
                ),
                timeout=12,
            )
            fact = (resp.get("content") or "").strip()
        except Exception:
            fact = "用户近期关注：" + "；".join(t[:60] for t in user_turns[-5:])

    if not fact:
        return None
    await store_episode(session, user_id, department, fact, category="fact")
    return fact
