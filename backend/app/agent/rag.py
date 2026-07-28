"""RAG 增强模块 (层级 3.2).

Retrieves department-isolated enterprise knowledge to ground the LLM and reduce
hallucination. In mock mode it uses keyword search (no embedding model needed);
with a real embedding endpoint it uses pg_vector cosine similarity.
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx
from sqlalchemy import case, func, or_, select

from app.config import settings
from app.db.models import Document, DocumentChunk

logger = logging.getLogger(__name__)

# 复用模块级 httpx 连接池，避免每次请求重建 TCP/TLS 连接
_http_client: "httpx.AsyncClient | None" = None


def _get_http_client() -> "httpx.AsyncClient":
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=20)
    return _http_client


async def embed_text(text: str) -> list[float]:
    if settings.MOCK_LLM:
        # placeholder vector; retrieval uses keyword match in mock mode
        return [0.0] * settings.EMBEDDING_DIM
    if not settings.EMBEDDING_BASE_URL:
        logger.warning("EMBEDDING_BASE_URL 未配置，RAG 回退到关键词检索（向量召回禁用）")
        return [0.0] * settings.EMBEDDING_DIM
    # Real: call internal embedding endpoint (bge-m3 / bge-large ...)
    client = _get_http_client()
    try:
        resp = await client.post(
            f"{settings.EMBEDDING_BASE_URL}/embeddings",
            json={"model": settings.EMBEDDING_MODEL, "input": text},  # bge-small-zh-v1.5 等本地模型
            headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        # 服务不可用（404/连接拒绝/超时等）时降级为零向量，由 retrieve 走关键词召回，
        # 避免单点 embedding 故障拖垮整个对话。
        logger.warning(
            "调用 embedding 失败（%s: %s）。RAG 回退到关键词检索。"
            "请确认 EMBEDDING_BASE_URL 指向真实的 embedding 服务（不能是本项目后端自身）。",
            type(e).__name__, e,
        )
        return [0.0] * settings.EMBEDDING_DIM


async def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """批量向量化（入库提速核心）：一次 HTTP 携带多段文本，避免逐 chunk 串行请求。

    返回与 texts 等长的向量列表；MOCK / 未配置 / 异常时降级为零向量。
    """
    if settings.MOCK_LLM or not settings.EMBEDDING_BASE_URL:
        return [[0.0] * settings.EMBEDDING_DIM for _ in texts]
    import httpx

    out: list[list[float]] = []
    client = _get_http_client()
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            resp = await client.post(
                f"{settings.EMBEDDING_BASE_URL}/embeddings",
                json={"model": settings.EMBEDDING_MODEL, "input": batch},
                headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        except Exception as e:  # noqa: BLE001
            logger.warning("批量 embedding 失败（%s），该批回退零向量", e)
            out.extend([0.0] * settings.EMBEDDING_DIM for _ in batch)
    return out


async def rerank(query: str, docs: list[str]) -> list[float]:
    """用 bge-reranker-v2-m3 对候选文档打分（OpenAI 兼容 /rerank 接口）。

    返回与 docs 等长的相关性分数；未配置或异常时返回 None，由调用方回退到向量序。
    """
    if settings.MOCK_LLM or not settings.RERANK_BASE_URL or not docs:
        return []
    try:
        headers = (
            {"Authorization": f"Bearer {settings.RERANK_API_KEY}"}
            if settings.RERANK_API_KEY and settings.RERANK_API_KEY != "EMPTY"
            else {}
        )
        client = _get_http_client()
        resp = await client.post(
            f"{settings.RERANK_BASE_URL}/rerank",
            json={"model": settings.RERANK_MODEL, "query": query, "documents": docs},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        scores = [0.0] * len(docs)
        for r in data.get("results", []):
            idx = r.get("index")
            if isinstance(idx, int) and 0 <= idx < len(scores):
                scores[idx] = float(r.get("relevance_score", 0.0))
        return scores
    except Exception:
        return []


def _dynamic_top_k(query: str) -> int:
    """动态 Top-K（RAG 设计要点 3.4）：简单问题取 2-3，复杂推理取 5-8。"""
    q = (query or "").strip()
    signals = 0
    signals += 1 if (q.count("？") + q.count("?")) >= 2 else 0
    signals += 1 if len(q) > 60 else 0
    signals += sum(1 for k in ("对比", "分析", "为什么", "如何", "步骤", "总结", "原因", "区别", "方案", "影响") if k in q)
    if signals >= 2:
        return 8
    if signals == 1:
        return 5
    return 3


async def _keyword_recall(session, query: str, depts: list, doc_types, limit: int) -> list[tuple]:
    """初筛层关键词召回：优先 pg_trgm 相似度（近似 BM25），失败回退 ILIKE。"""
    join_on = Document.id == DocumentChunk.document_id
    base = (
        select(DocumentChunk, Document.title)
        .join(Document, join_on)
        .where(DocumentChunk.department.in_(depts))
        .where(Document.doc_status == "active")
    )
    if doc_types:
        base = base.where(Document.doc_type.in_(doc_types))
    try:
        stmt = (
            select(DocumentChunk, Document.title, func.similarity(DocumentChunk.content, query).label("sim"))
            .join(Document, join_on)
            .where(DocumentChunk.department.in_(depts))
            .where(Document.doc_status == "active")
        )
        if doc_types:
            stmt = stmt.where(Document.doc_type.in_(doc_types))
        stmt = (
            stmt.where(func.similarity(DocumentChunk.content, query) > 0.1)
            .order_by(func.similarity(DocumentChunk.content, query).desc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        return [(c, t) for c, t, _ in res.all()]
    except Exception:
        tokens = [t for t in re.split(r"[\s，。、；,.;]+", query) if len(t) > 1][:6]
        if not tokens:
            return []
        conds = [DocumentChunk.content.ilike(f"%{t}%") for t in tokens]
        # 命中多个检索词的 chunk 相关性更高：按命中词数量降序，避免按插入顺序
        # 返回文档开头无关块（如把「员工手册」标题页排到「安全管理制度」之前）。
        matched = sum(case((cond, 1), else_=0) for cond in conds)
        stmt = (
            base.add_columns(matched.label("m"))
            .where(or_(*conds))
            .order_by(matched.desc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        return [(c, t) for c, t, _ in res.all()]


async def retrieve(
    session,
    query: str,
    department: str,
    limit: int | None = None,
    doc_types: list | None = None,
    user_id: str | None = None,
    include_episodic: bool = False,
) -> list[dict]:
    """混合检索（RAG 设计要点 3）：向量 + 关键词并行召回 → 元过滤 → 重排 → 动态 Top-K。

    返回字段含 meta（来源/页码/章节/权限），便于生成答案时标注引用来源。
    """
    depts = [department, "general"]
    top_k = limit if limit else _dynamic_top_k(query)

    # ---- 过滤层：元数据的硬过滤（部门 + 失效文档） ----
    cand_limit = max(top_k * 5, 20)
    meta_filter = [
        DocumentChunk.department.in_(depts),
        Document.doc_status == "active",
    ]
    if doc_types:
        meta_filter.append(Document.doc_type.in_(doc_types))

    if not settings.EMBEDDING_BASE_URL or settings.MOCK_LLM:
        # 演示模式 / 未配置 embedding 服务：关键词召回（含过滤层），避免使用零向量做余弦查询
        rows = await _keyword_recall(session, query, depts, doc_types, top_k)
        return [
            _chunk_to_dict(c, t, category="knowledge") for c, t in rows
        ][:top_k]

    # 1) 向量召回（bge-small-zh-v1.5）
    # pgvector 0.3.0 移除了 sqlalchemy.cosine_distance，统一用原生操作符 <=>（余弦距离）
    # query 向量化（HTTP）与关键词召回（DB）无依赖，并行发起以压低查询延迟
    vec, krows = await asyncio.gather(
        embed_text(query),
        _keyword_recall(session, query, depts, doc_types, cand_limit),
    )

    # pgvector 0.3.0 把模块级 cosine_distance 移到了 Vector 列类型的 comparator 方法上，
    # 正确用法是 embedding.cosine_distance(vec)（内部即 <=> 运算符，按距离升序=最相似在前）。
    vstmt = (
        select(
            DocumentChunk,
            Document.title,
            DocumentChunk.embedding.cosine_distance(vec).label("dist"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(*meta_filter)
        .order_by("dist")
        .limit(cand_limit)
    )
    vres = await session.execute(vstmt)
    vector_rows = [(c, t) for c, t, _ in vres.all()]

    # 3) 合并去重（以 chunk id 为准）
    merged: dict[str, tuple] = {}
    for c, t in vector_rows + krows:
        merged[c.id] = (c, t)
    candidates = [_chunk_to_dict(c, t, category="knowledge") for c, t in merged.values()]
    if not candidates:
        return []

    # 4) 精排层：Cross-Encoder（bge-reranker-v2-m3）对候选重排，取 Top-K
    # 重排前截断候选文本长度：cross-encoder 对超长文本做全注意力既慢又收益低，
    # 取前 512 字符已足以判断相关性；最终返回仍用原文，不影响答案质量。
    scores = await rerank(query, [c["content"][:512] for c in candidates])
    if scores:
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        candidates = [candidates[i] for i in order[:top_k]]
    else:
        candidates = candidates[:top_k]

    # 5) 长期情节记忆召回（可选，注入个性化上下文，置于知识块之后）
    if include_episodic and user_id:
        try:
            from app.agent.episodic import retrieve_episodes

            eps = await retrieve_episodes(session, query, user_id, department, limit=3)
            for e in eps:
                candidates.append({
                    "content": e, "title": "我的历史记忆", "department": department,
                    "meta": {"category": "episodic", "source": "episodic_memory"},
                    "category": "episodic",
                })
        except Exception:
            pass
    return candidates


def _chunk_to_dict(chunk, title: str, category: str = "knowledge") -> dict:
    meta = dict(chunk.meta or {})
    meta["category"] = category
    return {
        "content": chunk.content,
        "title": title,
        "department": chunk.department,
        "doc_type": meta.get("doc_type", ""),
        "page": meta.get("page"),
        "section": meta.get("section", ""),
        "source": meta.get("source", title),
        "meta": meta,
        "category": category,
    }
