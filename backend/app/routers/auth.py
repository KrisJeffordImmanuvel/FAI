from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import LoginIn
from ..security import create_token, verify_password
from ..services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEMO_ACCOUNTS = [
    {"role": "admin", "email": "admin@library.local", "password": "Admin@123", "name": "Dr. Kalpana Rao", "note": "Users, policies, agent settings, all analytics"},
    {"role": "librarian", "email": "librarian@library.local", "password": "Librarian@123", "name": "Ramesh Pai", "note": "Books, circulation, fines, approvals, notifications"},
    {"role": "member", "email": "member@library.local", "password": "Member@123", "name": "Aarav Sharma", "note": "Student — search, loans, fines, reservations, notifications"},
]


@router.get("/demo-accounts")
def demo_accounts() -> list[dict]:
    return DEMO_ACCOUNTS


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(403, "This account has been disabled")
    audit(db, "auth.login", "user", user.id, user)
    db.commit()
    return {"token": create_token(user.id, user.role), "user": S.user(user)}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return S.user(user)
