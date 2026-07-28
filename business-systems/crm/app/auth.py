"""CRM 身份鉴权：校验共享服务令牌并解析操作人（由网关/调用方透传身份头）。"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status as http_status

from app.config import settings


@dataclass
class Actor:
    """经网关透传的操作人身份。"""

    username: str
    role: str


async def get_actor(
    authorization: str = Header(None),
    x_act_user: str = Header(None, alias="X-Act-User"),
    x_act_role: str = Header(None, alias="X-Act-Role"),
) -> Actor:
    token = (authorization or "").replace("Bearer ", "").strip()
    if settings.SERVICE_TOKEN and token != settings.SERVICE_TOKEN:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED, detail="无效的服务令牌"
        )
    return Actor(username=x_act_user or "anonymous", role=x_act_role or "employee")
