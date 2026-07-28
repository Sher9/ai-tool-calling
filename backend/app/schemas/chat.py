from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatStep(BaseModel):
    tool: str
    display_name: str
    args: dict
    status: str  # pending/running/success/failed
    result: Any = None
    error: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    steps: list[ChatStep]
    used_rag: bool = False
    rag_sources: list = []


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
