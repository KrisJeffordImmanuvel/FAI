"""FastAPI dependencies: database session, authentication and role guards."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_token


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_token(authorization.split(" ", 1)[1])
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired — please sign in again")
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    return user


def require(*roles: str) -> Callable[[User], User]:
    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action requires role: {' or '.join(roles)}")
        return user

    return guard


staff = require("admin", "librarian")
admin_only = require("admin")


def own_member_or_staff(user: User, member_id: int) -> None:
    """Members may only access their own records."""
    if user.role == "member" and user.member_id != member_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only view your own records")
