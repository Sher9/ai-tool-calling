from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    display_name: str
    category: str
    description: str
    adapter: str
    parameters: dict
    allowed_roles: list
    enabled: bool
    mask_sensitive: bool
    requires_internet: bool


class ToolCreate(BaseModel):
    name: str
    display_name: str = ""
    category: str = "custom"
    description: str = ""
    adapter: str = ""
    parameters: dict = {}
    allowed_roles: list = []
    enabled: bool = True
    mask_sensitive: bool = True
    requires_internet: bool = False


class ToolUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    category: str | None = None
    adapter: str | None = None
    parameters: dict | None = None
    allowed_roles: list | None = None
    enabled: bool | None = None
    mask_sensitive: bool | None = None
    requires_internet: bool | None = None
