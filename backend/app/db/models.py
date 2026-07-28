"""ORM models for the platform.

Layers covered (storage layer / 层级 5):
  - users / roles / permissions   (RBAC)
  - tools                          (tool registry / 工具注册中心)
  - conversations / messages       (memory)
  - audit_logs                     (operation audit / 操作审计)
  - task_records                   (multi-step task plans)
  - documents / document_chunks    (knowledge base + pg_vector RAG)
  - prompts                        (prompt template management)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# RBAC: users
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    # bcrypt hash; empty for the seed admin convenience (handled in seed)
    password_hash: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(32), default="employee")  # admin/employee/finance/tech/sales/hr
    department: Mapped[str] = mapped_column(String(64), default="general")  # general/tech/sales/finance/hr
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


# --------------------------------------------------------------------------- #
# Tool registry (层级 3.1)
# --------------------------------------------------------------------------- #
class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    # Technical name used by the LLM function-calling, e.g. "crm_query"
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    category: Mapped[str] = mapped_column(String(64), default="office")  # office/dev/business/compute/custom/external
    description: Mapped[str] = mapped_column(Text, default="")
    # Adapter identifier -> maps to tools/adapters implementation
    adapter: Mapped[str] = mapped_column(String(128), default="")
    # JSON-Schema for parameters (function calling spec)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Allowed roles; empty list means "all authenticated users"
    allowed_roles: Mapped[list] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Whether tool output should be passed through data masking
    mask_sensitive: Mapped[bool] = mapped_column(Boolean, default=True)
    # Whether this tool requires internet (gated by EXTERNAL_TOOLS_ENABLED)
    requires_internet: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------- #
# Memory: conversations & messages
# --------------------------------------------------------------------------- #
class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all,delete")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, default="")
    # structured tool-call/result data for visualization
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


# --------------------------------------------------------------------------- #
# Audit log (操作审计)
# --------------------------------------------------------------------------- #
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)  # tool_call / login / admin_op / sensitive_alert
    resource: Mapped[str] = mapped_column(String(256), default="")
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    # True when the action touched sensitive data
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


# --------------------------------------------------------------------------- #
# Task records (multi-step plan execution history)
# --------------------------------------------------------------------------- #
class TaskRecord(Base):
    __tablename__ = "task_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    plan: Mapped[dict] = mapped_column(JSONB, default=dict)  # steps + results
    status: Mapped[str] = mapped_column(String(32), default="success")  # success/failed/partial
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------- #
# Knowledge base (RAG, 层级 3.2) + pg_vector
# --------------------------------------------------------------------------- #
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256))
    # department that is allowed to see this doc (isolated knowledge base)
    department: Mapped[str] = mapped_column(String(64), default="general")
    file_path: Mapped[str] = mapped_column(String(512), default="")  # MinIO object key

    # ----- 数据治理 / 元数据（RAG 设计要点 2/4/5） -----
    doc_type: Mapped[str] = mapped_column(String(32), default="general")  # faq/regulation/manual/book/general
    trust_level: Mapped[str] = mapped_column(String(32), default="internal")  # official/internal/external
    source: Mapped[str] = mapped_column(String(512), default="")  # 文档来源 / 出处 URL
    tags: Mapped[list] = mapped_column(JSONB, default=list)  # 业务标签

    # ----- 版本管理（RAG 设计要点 5） -----
    version: Mapped[int] = mapped_column(Integer, default=1)
    doc_status: Mapped[str] = mapped_column(String(32), default="active")  # active/expired/superseded
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # ----- 索引状态 -----
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="indexed")  # indexed/failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str] = mapped_column(String(64), default="")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    department: Mapped[str] = mapped_column(String(64), default="general", index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIM))

    # ----- 溯源 / 元数据（RAG 设计要点 4） -----
    # meta: {source, title, page, section, doc_type, permission, tags, updated_at}
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class EpisodicMemory(Base):
    """长期情节记忆（Agent 记忆机制 · 层级 3）：跨会话沉淀用户偏好与历史关键事实。

    每次对话结束后由 LLM 抽取关键事实向量化入库，下次对话时按语义召回。
    """

    __tablename__ = "episodic_memories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    department: Mapped[str] = mapped_column(String(64), default="general", index=True)
    content: Mapped[str] = mapped_column(Text)  # 抽取后的关键事实 / 对话摘要
    category: Mapped[str] = mapped_column(String(32), default="fact")  # fact/preference/event
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------- #
# Prompt templates (层级 3.6)
# --------------------------------------------------------------------------- #
class PromptTemplate(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
