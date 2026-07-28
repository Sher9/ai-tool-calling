"""知识库工具: vector_search（RAG 检索）.

- vector_search: 复用 app.agent.rag.retrieve 的混合检索（向量+关键词→重排→动态 Top-K）。
"""
from __future__ import annotations

import re

from app.db.base import async_session_maker
from app.tools.base import ToolContext, ToolResult, fail, ok_text


# ============================================================
# 1) 知识库向量检索
# ============================================================
# 单片段超过该字数时才做「基于 query 的答案抽取」而非整段返回。
# 配合按章节切片（regulation 每章独立成块，通常 ≤400 字），绝大多数命中片段不触发截断。
_ANSWER_EXTRACT_THRESHOLD = 400

# 进入 RAG 的 query 噪音词（路由词），带入会稀释相似度
_KB_QUERY_NOISE = [
    "知识库", "检索", "查询", "查看", "搜索", "查一下", "找一下", "找", "帮我查",
    "帮我检索", "请查", "请问", "我想知道", "我需要", "我想了解", "关于", "相关的",
    "资料", "库里", "库中", "文档库", "在文档里", "里面", "向量检索", "语义检索",
]


def _clean_query(q: str) -> str:
    s = q
    for w in _KB_QUERY_NOISE:
        s = s.replace(w, "")
    s = re.sub(r"\s+", " ", s).strip()
    return s or q.strip()


async def vector_search(args: dict, ctx: ToolContext) -> ToolResult:
    query = _clean_query((args.get("query") or "").strip())
    if not query:
        return fail("缺少 query 参数")
    top_k = int(args.get("top_k", 5))
    metadata_filter = args.get("metadata_filter") or {}
    doc_types = metadata_filter.get("doc_types") if isinstance(metadata_filter, dict) else None

    async with async_session_maker() as session:
        from app.agent.rag import retrieve

        chunks = await retrieve(
            session,
            query=query,
            department=ctx.department,
            limit=top_k,
            doc_types=doc_types,
            user_id=ctx.user_id,
            include_episodic=False,
        )
    if not chunks:
        return ok_text("知识库中未检索到相关内容（受部门权限与文档状态限制）。")
    note = "（已按问题抽取最相关片段，供生成答案引用）"
    return ok_text(note + "\n" + _fmt_chunks(chunks, query))


# 章节标题模式：用于从命中的长正文里定位「第X章/第X条 标题」整体区间
_SECTION_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百零\d]+[章条节篇编部分]|[CHS]\.?\d+|[0-9]+)[\s、.．:-]+[^\s\d][^\n]{0,30}\s*$",
    re.MULTILINE,
)


def _extract_answer(content: str, query: str) -> str:
    """从命中的长正文里抽取与 query 最相关的片段，避免把整段文档原样返回。

    抽取优先级：
    1. 章节级：若正文含「第X章 标题」式章节，且 query 命中所属章节标题，
       则整体返回「该章节标题 → 下一章节标题前」的完整内容（制度类最精准）；
    2. 句子级：取含 query 关键词的句子并向前/后各扩展 2 句（保证条款完整）；
    3. 兜底：无字面命中时返回前 3 句作预览。
    """
    query_terms = [t for t in re.split(r"[\s，。、；,.;?？!！]+", query) if len(t) > 1]

    # 1) 章节级定位：content 由多个章节组成（如切片未完全拆开时）
    sections = _split_sections(content)
    if len(sections) > 1:
        for title, body in sections:
            title_core = re.sub(r"^(?:第[一二三四五六七八九十百零\d]+[章条节篇编部分]|[CHS]\.?\d+|[0-9]+)[\s、.．:-]*", "", title)
            if any(t in title_core or t in title for t in query_terms):
                return (title + "\n" + body).strip()
        # query 未匹配具体章节标题，但命中有章节 → 退回句子级在整段上抽取
        content_joined = content
    else:
        content_joined = content

    # 2) 句子级抽取
    sentences = re.split(r"(?<=[。！？!?\n])", content_joined)
    sentences = [s for s in sentences if s.strip()]
    if not sentences:
        return content

    scored = []
    for i, s in enumerate(sentences):
        hit = sum(1 for t in query_terms if t in s)
        scored.append((i, hit))
    scored.sort(key=lambda x: x[1], reverse=True)
    best_idx, best_hit = scored[0]
    if best_hit == 0:
        # 无任何关键词命中（语义相关但字面不重叠）：返回前三句作预览
        return "".join(sentences[:3]).strip()
    lo = max(0, best_idx - 2)
    hi = min(len(sentences), best_idx + 3)
    return "".join(sentences[lo:hi]).strip()


def _split_sections(text: str) -> list[tuple[str, str]]:
    """把含多个章节标题的正文拆成 [(标题, 正文), ...]；无章节时整体返回。"""
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return []
    out: list[tuple[str, str]] = []
    for idx, m in enumerate(matches):
        title = m.group(0).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        out.append((title, body))
    return out


def _fmt_chunks(chunks: list[dict], query: str = "") -> str:
    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("meta", {}) or {}
        src = meta.get("source") or c.get("title") or "未知"
        content = c.get("content", "") or ""
        # 长正文：抽取与 query 最相关的片段，避免整段文档灌给模型导致答非所问
        if query and len(content) > _ANSWER_EXTRACT_THRESHOLD:
            content = _extract_answer(content, query)
        # 若命中片段本身就是一个独立章节（pre-chapter 切片），且其 section 标题
        # 与 query 相关，直接展示整章（已由切片保证为一整块，无需再截）。
        ref = f"[来源:{src}"
        if meta.get("page"):
            ref += f"|页码:{meta['page']}"
        if meta.get("section"):
            ref += f"|章节:{meta['section']}"
        ref += "]"
        lines.append(f"【片段{i}】{ref}\n{content}")
    return "\n\n".join(lines)


ADAPTERS = {
    "vector_search": vector_search,
}
