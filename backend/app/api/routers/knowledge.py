"""Knowledge base management (层级 3.2): upload -> parse -> vectorize -> pg_vector.

覆盖 RAG 设计要点：
  - 上传携带 doc_type / trust_level / tags / source（数据治理与元数据）
  - 版本管理：同标题重传自动将旧版标记 superseded，支持回滚
  - 全量校验：/validate 输出知识库健康度报告
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.security import get_current_user
from app.db.models import Document, User
from app.services.file_processing import ingest_file
from app.services.knowledge_maintenance import validate_knowledge_base

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

logger = logging.getLogger("knowledge")

VALID_DOC_TYPES = {"faq", "regulation", "manual", "book", "general"}


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    department: str = Form(None),
    doc_type: str = Form("general"),
    trust_level: str = Form("internal"),
    tags: str = Form(""),
    source: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role != "admin" and department and department != user.department:
        raise HTTPException(status_code=403, detail="仅管理员可上传到其他部门知识库")
    dep = department or user.department
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")

    doc_type = doc_type if doc_type in VALID_DOC_TYPES else "general"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # 版本管理：存在同名活跃文档则将其置为 superseded，保留历史可回滚
    old = None
    res = await session.execute(
        select(Document).where(
            Document.title == file.filename,
            Document.department == dep,
            Document.doc_status == "active",
        )
    )
    old = res.scalars().first()

    try:
        doc = await ingest_file(
            session, data, file.filename, dep, user.id,
            doc_type=doc_type, trust_level=trust_level, tags=tag_list, source=source,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("文档入库失败（file=%s, dep=%s）", file.filename, dep)
        raise HTTPException(status_code=500, detail=f"文档入库失败：{type(e).__name__}: {e}")
    if old:
        old.doc_status = "superseded"
        doc.version = old.version + 1
        doc.parent_id = old.id
        await session.commit()
        await session.refresh(doc)

    return {
        "id": doc.id, "title": doc.title, "department": doc.department,
        "doc_type": doc.doc_type, "version": doc.version, "chunk_count": doc.chunk_count,
    }


@router.get("")
async def list_docs(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stmt = select(Document)
    if user.role != "admin":
        stmt = stmt.where(Document.department.in_([user.department, "general"]))
    stmt = stmt.order_by(Document.created_at.desc())
    res = await session.execute(stmt)
    return [
        {
            "id": d.id, "title": d.title, "department": d.department,
            "doc_type": d.doc_type, "trust_level": d.trust_level, "tags": d.tags,
            "version": d.version, "doc_status": d.doc_status, "chunk_count": d.chunk_count,
            "created_at": d.created_at.isoformat(),
        }
        for d in res.scalars().all()
    ]


@router.post("/{doc_id}/rollback")
async def rollback(doc_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可回滚版本")
    target = await session.get(Document, doc_id)
    if not target:
        raise HTTPException(status_code=404, detail="文档不存在")
    # 将同一 (标题, 部门) 的其它版本置为失效，恢复目标版本为 active
    res = await session.execute(
        select(Document).where(Document.title == target.title, Document.department == target.department)
    )
    for d in res.scalars().all():
        d.doc_status = "active" if d.id == target.id else "superseded"
    await session.commit()
    return {"ok": True, "active_id": target.id}


@router.post("/validate")
async def validate(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行全量校验")
    return await validate_knowledge_base(session)


@router.delete("/{doc_id}")
async def delete_doc(doc_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if user.role != "admin" and doc.department != user.department:
        raise HTTPException(status_code=403, detail="无权删除该文档")
    await session.delete(doc)
    await session.commit()
    return {"ok": True}
