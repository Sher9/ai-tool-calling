"""知识库维护（RAG 设计要点 5）：定时全量校验。

扫描全库，输出健康度报告：失效/过期文档、无分块的损坏文档、重复分块等。
可作为每月定时任务调用。
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import Document, DocumentChunk


async def validate_knowledge_base(session) -> dict:
    # 文档状态分布
    status_rows = (await session.execute(
        select(Document.doc_status, func.count()).group_by(Document.doc_status)
    )).all()
    doc_status = {s: c for s, c in status_rows}
    total_docs = sum(doc_status.values())

    # 分块总数
    total_chunks = (await session.execute(select(func.count()).select_from(DocumentChunk))).scalar() or 0

    # 活跃但无分块的文档（损坏 / 索引失败）
    sub = select(DocumentChunk.document_id)
    broken = (await session.execute(
        select(func.count()).select_from(Document).where(Document.doc_status == "active").where(Document.id.notin_(sub))
    )).scalar() or 0

    # 重复分块（同部门 + 相同内容）
    dup_groups = (await session.execute(
        select(func.count()).select_from(
            select(DocumentChunk.department)
            .group_by(DocumentChunk.department, func.md5(DocumentChunk.content))
            .having(func.count(DocumentChunk.id) > 1)
        )
    )).scalar() or 0

    return {
        "total_docs": total_docs,
        "doc_status_breakdown": doc_status,
        "total_chunks": total_chunks,
        "active_docs_without_chunks": broken,
        "duplicate_chunk_groups": dup_groups,
    }
