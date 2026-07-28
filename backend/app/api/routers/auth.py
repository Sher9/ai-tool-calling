"""Authentication: login (JWT) and current-user info."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.audit import write_audit
from app.core.security import create_access_token, get_current_user, verify_password
from app.db.models import User
from app.schemas.common import Token
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(User).where(User.username == form.username)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()
    if not user or user.disabled or not verify_password(form.password, user.password_hash):
        await write_audit(
            session, action="login_failed", resource=form.username,
            detail={"reason": "bad_credentials"}, commit=False,
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(user.id, user.role, user.department)
    await write_audit(session, user_id=user.id, username=user.username, action="login", resource="auth")
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
