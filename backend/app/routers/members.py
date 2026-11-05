from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user, own_member_or_staff, staff
from ..models import Fine, Loan, Member, Notification, Reservation, User
from ..schemas import MemberIn, MemberStatusIn, MemberUpdate, PreferencesIn
from ..security import hash_password
from ..services import circulation
from ..services.audit import audit
from ..services.settings import today
from .common import paginate

router = APIRouter(prefix="/api", tags=["members"])


@router.get("/members")
def list_members(
    q: str = Query("", max_length=100),
    member_type: str = Query("", pattern="^(|student|faculty|staff)$"),
    status: str = Query("", pattern="^(|active|restricted|suspended)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(staff),
) -> dict:
    query = select(Member).order_by(Member.name)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Member.name.ilike(like), Member.code.ilike(like), Member.email.ilike(like), Member.department.ilike(like)))
    if member_type:
        query = query.where(Member.member_type == member_type)
    if status:
        query = query.where(Member.status == status)
    result = paginate(db, query, page, page_size, lambda m: m)
    stats = circulation.member_stats(db, [m.id for m in result["items"]], today(db))
    result["items"] = [S.member(m, stats.get(m.id)) for m in result["items"]]
    return result


def member_detail(db: Session, member: Member) -> dict:
    on = today(db)
    stats = circulation.member_stats(db, [member.id], on)[member.id]
    policy = circulation.get_policy(db, member.member_type)
    out = S.member(member, stats)
    out["policy"] = {"label": policy.label, "max_loans": policy.max_loans, "loan_days": policy.loan_days, "max_renewals": policy.max_renewals,
                     "max_reservations": policy.max_reservations, "grace_days": policy.grace_days, "max_fine": policy.max_fine}
    loans = db.scalars(select(Loan).where(Loan.member_id == member.id).order_by(Loan.issued_on.desc())).all()
    out["active_loans"] = [S.loan(lo, on) for lo in loans if lo.status == "active"]
    out["history"] = [S.loan(lo, on, include_risk=False) for lo in loans if lo.status != "active"][:50]
    res = db.scalars(select(Reservation).where(Reservation.member_id == member.id).order_by(Reservation.created_at.desc())).all()
    positions = {}
    for r in res:
        if r.status == "waiting":
            positions[r.id] = (db.scalar(select(func.count(Reservation.id)).where(Reservation.book_id == r.book_id, Reservation.status == "waiting",
                                                                                 Reservation.created_at <= r.created_at)) or 1)
    out["reservations"] = [S.reservation(r, positions.get(r.id)) for r in res[:30]]
    out["fines"] = [S.fine(f) for f in db.scalars(select(Fine).where(Fine.member_id == member.id).order_by(Fine.created_on.desc())).all()]
    return out


@router.get("/members/{member_id}")
def get_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    own_member_or_staff(user, member_id)
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(404, "Member not found")
    return member_detail(db, member)


@router.get("/me/summary")
def my_summary(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if user.member_id is None:
        raise HTTPException(404, "This account is not linked to a library membership")
    member = db.get(Member, user.member_id)
    assert member is not None
    out = member_detail(db, member)
    out["unread_notifications"] = db.scalar(select(func.count(Notification.id)).where(Notification.member_id == member.id, Notification.status == "sent")) or 0
    out["sim_date"] = today(db).isoformat()
    return out


@router.put("/me/preferences")
def set_preferences(body: PreferencesIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if user.member_id is None:
        raise HTTPException(404, "Not a member account")
    member = db.get(Member, user.member_id)
    assert member is not None
    member.notify_pref = body.notify_pref
    audit(db, "member.preferences", "member", member.id, user, {"notify_pref": body.notify_pref})
    db.commit()
    return S.member(member)


def create_member_account(db: Session, *, name: str, email: str, phone: str, member_type: str, department: str,
                          notify_pref: str, password: str | None) -> tuple[Member, User | None]:
    """Create a member (and optionally their login). Shared by staff creation and self sign-up."""
    email = email.lower()
    if db.scalar(select(Member.id).where(Member.email == email)) or db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists — try signing in instead")
    prefix = {"student": "S", "faculty": "F", "staff": "T"}[member_type]
    n = (db.scalar(select(func.count(Member.id)).where(Member.member_type == member_type)) or 0) + 1
    code = f"{prefix}{9000 + n}"
    while db.scalar(select(Member.id).where(Member.code == code)):
        n += 1
        code = f"{prefix}{9000 + n}"
    m = Member(code=code, name=name, email=email, phone=phone, member_type=member_type, department=department,
               joined_on=today(db), status="active", notify_pref=notify_pref)
    db.add(m)
    db.flush()
    user = None
    if password is not None:
        user = User(email=email, name=name, password_hash=hash_password(password), role="member", member_id=m.id)
        db.add(user)
        db.flush()
    return m, user


@router.post("/members", status_code=201)
def create_member(body: MemberIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    m, _ = create_member_account(db, name=body.name, email=body.email, phone=body.phone, member_type=body.member_type,
                                 department=body.department, notify_pref=body.notify_pref,
                                 password="Member@123" if body.create_login else None)
    audit(db, "member.create", "member", m.id, user, {"code": m.code, "type": body.member_type})
    db.commit()
    return S.member(m) | {"initial_password": "Member@123" if body.create_login else None}


@router.put("/members/{member_id}")
def update_member(member_id: int, body: MemberUpdate, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    m = db.get(Member, member_id)
    if m is None:
        raise HTTPException(404, "Member not found")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(m, k, v)
    if m.user and "name" in changes:
        m.user.name = changes["name"]
    audit(db, "member.update", "member", m.id, user, changes)
    db.commit()
    return S.member(m)


@router.post("/members/{member_id}/status")
def set_member_status(member_id: int, body: MemberStatusIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    """Restricting or suspending is a high-impact human decision and requires a reason."""
    m = db.get(Member, member_id)
    if m is None:
        raise HTTPException(404, "Member not found")
    if body.status != "active" and len(body.reason.strip()) < 5:
        raise HTTPException(422, "A reason (at least 5 characters) is required to restrict or suspend a member")
    m.status = body.status
    m.restriction_reason = body.reason.strip() or None if body.status != "active" else None
    audit(db, "member.status", "member", m.id, user, {"status": body.status, "reason": body.reason})
    db.commit()
    return S.member(m)
