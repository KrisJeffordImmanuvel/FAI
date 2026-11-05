from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import ChangePasswordIn, LoginIn, RegisterIn
from ..security import create_token, hash_password, verify_password
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


@router.get("/demo-members")
def demo_members() -> list[dict]:
    """The other seeded member logins (static seed data — never reads real accounts from the database)."""
    from ..seed import MEMBERS, _email

    return [{"name": name, "email": _email(name), "member_type": mtype, "department": dept, "password": "Member@123"}
            for name, mtype, dept, _pref, _habit in MEMBERS if name != "Aarav Sharma"]


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    """Self-service sign-up for library members. Staff accounts can only be created by an admin."""
    from .members import create_member_account

    member, user = create_member_account(db, name=body.name, email=body.email, phone=body.phone, member_type=body.member_type,
                                         department=body.department, notify_pref=body.notify_pref, password=body.password)
    assert user is not None
    audit(db, "auth.register", "member", member.id, user, {"code": member.code, "type": member.member_type})
    db.commit()
    return {"token": create_token(user.id, user.role), "user": S.user(user), "member_code": member.code}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Your current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(400, "Choose a password different from your current one")
    user.password_hash = hash_password(body.new_password)
    audit(db, "auth.change_password", "user", user.id, user)
    db.commit()
    return {"ok": True}
