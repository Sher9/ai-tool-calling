"""Role-based access control helpers."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.models import Tool, User

# Role hierarchy is flat; "admin" can access everything.
ROLE_ALL = "*"
ADMIN_ROLE = "admin"


def role_can_use_tool(user: User, tool: Tool) -> bool:
    """Return True if the user's role is permitted to use the tool."""
    if user.role == ADMIN_ROLE:
        return True
    if not tool.allowed_roles:
        return True  # empty => all authenticated employees
    return user.role in tool.allowed_roles


def require_role(required: list[str] | str):
    """Dependency factory that limits an endpoint to given role(s)."""
    if isinstance(required, str):
        required = [required]

    async def checker(user: User = Depends(get_current_user)) -> User:
        if ADMIN_ROLE not in required and user.role not in required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"当前角色({user.role})无权访问该资源",
            )
        return user

    return checker
