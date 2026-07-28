"""一次性脚本：按最新切片策略（章节边界切分）重新索引知识库中已入库的制度类文档。

背景：
  - 旧切片把「第九章 安全管理制度」与「离职交接」「第十章 附则」混进同一 chunk，
    导致检索「安全管理制度」时返回整段无关内容。
  - 本脚本遍历所有 active 的 regulation / general 文档，按新策略（章节边界优先）重新切分并重向量化。

重建来源（两种，自动回退）：
  1. 优先用原始文件（MinIO / 本地回退）重新解析 + 章节切分，最完整；
  2. 若原始文件暂不可用（如 MinIO 未启动），则从现有 chunk 的文本内容按章节边界再次切分
     ——粗 chunk 内通常含完整章节，再切即可把「第九章 安全管理制度」拆成独立向量块。

用法（在 backend/ 目录下）：
    python reindex_regulations.py            # 仅重索引 regulation + general
    python reindex_regulations.py --all      # 重索引全部类型
    python reindex_regulations.py --dry      # 只打印将要处理的文档，不做写操作
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text

from app.db.base import async_session_maker, Base, engine
from app.db.models import Document, DocumentChunk
from app.agent.rag import embed_text
from app.services.file_processing import extract_pages, split_document, _clean_text
from app.core.storage import get_object_bytes


async def rebuild_from_existing(doc: Document, existing: list[DocumentChunk], dry: bool) -> int:
    """原文件不可用：把现有 chunk 文本聚合为整篇，按章节边界重新切分。"""
    full = "\n".join(c.content for c in existing if c.content)
    out = split_document(doc.title, full, doc.doc_type)
    print(f"  -> 从现有 {len(existing)} 个旧 chunk 聚合重切为 {len(out)} 个章节 chunk")
    if dry:
        return 0
    async with async_session_maker() as session:
        for c in existing:
            await session.delete(c)
        meta_base = {
            "source": doc.title, "title": doc.title, "doc_type": doc.doc_type,
            "permission": doc.department, "tags": doc.tags, "updated_at": doc.created_at.isoformat(),
        }
        for i, part in enumerate(out):
            emb = await embed_text(part["content"])
            meta = dict(meta_base)
            if part.get("section"):
                meta["section"] = part["section"]
            session.add(DocumentChunk(
                document_id=doc.id, department=doc.department,
                content=part["content"], embedding=emb, chunk_index=i, meta=meta,
            ))
        doc.chunk_count = len(out)
        await session.commit()
    return len(out)


async def rebuild_from_file(doc: Document, dry: bool) -> int:
    data = await get_object_bytes(doc.file_path)
    if not data:
        return -1  # 标记需要回退
    text_all = _clean_text("\n".join(t for _, t in extract_pages(doc.title, data)))
    parts = split_document(doc.title, text_all, doc.doc_type)
    print(f"  -> 从原文件重新切分为 {len(parts)} 个 chunk")
    if dry:
        return 0
    async with async_session_maker() as session:
        old = await session.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        for c in old.scalars().all():
            await session.delete(c)
        meta_base = {
            "source": doc.title, "title": doc.title, "doc_type": doc.doc_type,
            "permission": doc.department, "tags": doc.tags, "updated_at": doc.created_at.isoformat(),
        }
        for i, part in enumerate(parts):
            emb = await embed_text(part["content"])
            meta = dict(meta_base)
            if part.get("section"):
                meta["section"] = part["section"]
            session.add(DocumentChunk(
                document_id=doc.id, department=doc.department,
                content=part["content"], embedding=emb, chunk_index=i, meta=meta,
            ))
        doc.chunk_count = len(parts)
        await session.commit()
    return len(parts)


async def main() -> None:
    dry = "--dry" in sys.argv
    all_types = "--all" in sys.argv
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        await conn.run_sync(Base.metadata.create_all)

    stmt = select(Document).where(Document.doc_status == "active")
    if not all_types:
        stmt = stmt.where(Document.doc_type.in_(["regulation", "general"]))
    async with async_session_maker() as session:
        res = await session.execute(stmt)
        docs = res.scalars().all()
    print(f"待重新索引文档数：{len(docs)}（{'全类型' if all_types else 'regulation+general'}{' [dry-run]' if dry else ''}）")

    total = 0
    for d in docs:
        print(f"[处理] {d.title} (id={d.id}, type={d.doc_type})")
        async with async_session_maker() as s:
            r = await s.execute(select(DocumentChunk).where(DocumentChunk.document_id == d.id))
            existing = r.scalars().all()
        if not existing:
            print("  ! 无现有 chunk，跳过")
            continue
        # 优先用原文件重新解析；MinIO 不可用时回退到「聚合现有 chunk 内容按章节重切」
        n = await rebuild_from_file(d, dry)
        if n == -1:
            print("  (原文件不可用，回退：聚合现有 chunk 按章节重切)")
            n = await rebuild_from_existing(d, existing, dry)
        if n:
            total += n
    print(f"完成。共重索引 chunk 数：{total}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        import traceback
        traceback.print_exc()
