from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    display_name: str = ""
    password: str
    role: str = "employee"
    department: str = "general"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    role: str
    department: str
    disabled: bool
    created_at: datetime
