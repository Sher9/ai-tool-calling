"""OA 库表：审批单 / 审批节点。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OaApproval(Base):
    __tablename__ = "oa_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), default="")  # 请假/出差/报销/采购
    applicant: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="审批中")  # 审批中/已通过/已驳回
    current_node: Mapped[str] = mapped_column(String(32), default="")  # 当前待审批节点名
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class OaApprovalNode(Base):
    __tablename__ = "oa_approval_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("oa_approvals.id", ondelete="CASCADE"))
    node_name: Mapped[str] = mapped_column(String(32), default="")  # 部门主管/财务/人事/总经理
    seq: Mapped[int] = mapped_column(Integer, default=0)
    approver: Mapped[str] = mapped_column(String(64), default="")  # 应审批人(平台用户名)
    status: Mapped[str] = mapped_column(String(16), default="待审批")  # 待审批/已通过/已驳回
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
