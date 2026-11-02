from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import admin_only, staff
from ..models import AuditLog, Holiday, Policy, User
from ..schemas import AgentSettingsIn, HolidayIn, PolicyIn, UserIn, UserUpdate
from ..security import hash_password
from ..services import fines as fine_engine
from ..services.audit import audit
from ..services.settings import all_settings, set_setting

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _policy(p: Policy) -> dict:
    return {c: getattr(p, c) for c in ("id", "member_type", "label", "max_loans", "loan_days", "max_renewals", "max_reservations", "grace_days",
                                       "fine_slabs", "max_fine", "exclude_sundays", "lost_after_days", "lost_processing_fee", "hold_days")}


@router.get("/users")
def users(db: Session = Depends(get_db), _user: User = Depends(admin_only)) -> list[dict]:
    return [S.user(u) for u in db.scalars(select(User).order_by(User.role, User.name))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    if db.scalar(select(User.id).where(User.email == body.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    u = User(email=body.email.lower(), name=body.name, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit(db, "user.create", "user", u.id, user, {"email": u.email, "role": u.role})
    db.commit()
    return S.user(u)


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == user.id and body.is_active is False:
        raise HTTPException(400, "You cannot disable your own account")
    if body.name:
        u.name = body.name
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
    audit(db, "user.update", "user", u.id, user, {"is_active": u.is_active, "password_changed": bool(body.password)})
    db.commit()
    return S.user(u)


@router.get("/policies")
def policies(db: Session = Depends(get_db), _user: User = Depends(staff)) -> list[dict]:
    return [_policy(p) for p in db.scalars(select(Policy).order_by(Policy.id))]


@router.put("/policies/{member_type}")
def update_policy(member_type: str, body: PolicyIn, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    p = db.scalar(select(Policy).where(Policy.member_type == member_type))
    if p is None:
        raise HTTPException(404, "Policy not found")
    data = body.model_dump()
    errors = fine_engine.validate_slabs(data["fine_slabs"])
    if errors:
        raise HTTPException(422, {"message": "Invalid fine slabs", "errors": errors})
    for k, v in data.items():
        setattr(p, k, v)
    audit(db, "policy.update", "policy", p.id, user, data)
    db.commit()
    return _policy(p)


@router.get("/holidays")
def holidays(db: Session = Depends(get_db), _user: User = Depends(staff)) -> list[dict]:
    return [{"id": h.id, "date": h.date.isoformat(), "name": h.name} for h in db.scalars(select(Holiday).order_by(Holiday.date))]


@router.post("/holidays", status_code=201)
def add_holiday(body: HolidayIn, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    h = Holiday(date=body.date, name=body.name)
    db.add(h)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A holiday already exists on that date") from None
    audit(db, "holiday.create", "holiday", h.id, user, {"date": body.date.isoformat(), "name": body.name})
    db.commit()
    return {"id": h.id, "date": h.date.isoformat(), "name": h.name}


@router.delete("/holidays/{holiday_id}", status_code=204, response_class=Response, response_model=None)
def delete_holiday(holiday_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> None:
    h = db.get(Holiday, holiday_id)
    if h is None:
        raise HTTPException(404, "Holiday not found")
    audit(db, "holiday.delete", "holiday", h.id, user, {"date": h.date.isoformat()})
    db.delete(h)
    db.commit()
    return Response(status_code=204)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    return all_settings(db)


@router.put("/settings")
def put_settings(body: AgentSettingsIn, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    changes = body.model_dump(exclude_none=True)
    current = all_settings(db)
    if "cooldown_days" in changes:
        changes["cooldown_days"] = current["cooldown_days"] | changes["cooldown_days"]
    for k, v in changes.items():
        set_setting(db, k, v)
    audit(db, "settings.update", "settings", None, user, changes)
    db.commit()
    return all_settings(db)


@router.get("/audit")
def audit_log(
    limit: int = Query(100, ge=1, le=500),
    action: str = Query("", max_length=60),
    db: Session = Depends(get_db),
    _user: User = Depends(staff),
) -> list[dict]:
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        q = q.where(AuditLog.action.ilike(f"{action}%"))
    return [S.audit(a) for a in db.scalars(q.limit(limit))]
