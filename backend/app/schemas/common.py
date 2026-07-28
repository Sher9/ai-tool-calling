from __future__ import annotations

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthStatus(BaseModel):
    status: str
    components: dict
