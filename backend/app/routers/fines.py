from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user, own_member_or_staff, staff
from ..models import Approval, Fine, User
from ..schemas import DecisionIn, FinePreviewIn, PaymentIn, WaiverIn, WaiverRequestIn
from ..services import circulation, oversight
from ..services import fines as fine_engine
from .common import paginate

router = APIRouter(prefix="/api", tags=["fines"])


@router.get("/fines")
def list_fines(
    status: str = Query("unpaid", pattern="^(unpaid|accruing|open|partially_paid|paid|waived|all)$"),
    member_id: int | None = Query(None, gt=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    if user.role == "member":
        member_id = user.member_id
    query = select(Fine).order_by(Fine.last_computed_on.desc(), Fine.id.desc())
    if status == "unpaid":
        query = query.where(Fine.status.in_(circulation.OPEN_FINE_STATUSES))
    elif status != "all":
        query = query.where(Fine.status == status)
    if member_id:
        query = query.where(Fine.member_id == member_id)
    return paginate(db, query, page, page_size, S.fine)


@router.get("/fines/{fine_id}")
def get_fine(fine_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise HTTPException(404, "Fine not found")
    own_member_or_staff(user, fine.member_id)
    return S.fine(fine, detail=True)


@router.post("/fines/preview")
def preview(body: FinePreviewIn, db: Session = Depends(get_db), _user: User = Depends(current_user)) -> dict:
    """Fine calculator: runs the same deterministic engine without touching any data."""
    if body.returned_on < body.due_on:
        return fine_engine.compute_overdue_fine(body.due_on, body.due_on, fine_engine.FinePolicy((), 0, 0)).to_dict()
    if (body.returned_on - body.due_on).days > 400:
        raise HTTPException(422, "Please choose dates within about a year")
    policy = circulation.get_policy(db, body.member_type)
    fp = circulation.fine_policy(policy)
    holidays = circulation.holiday_dates(db)
    if body.lost:
        return fine_engine.compute_lost_fine(body.due_on, body.returned_on, fp, body.replacement_cost, holidays).to_dict()
    return fine_engine.compute_overdue_fine(body.due_on, body.returned_on, fp, holidays).to_dict()


@router.post("/fines/{fine_id}/payments")
def pay(fine_id: int, body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    fine = circulation.record_payment(db, fine_id, body.amount, body.method, user)
    db.commit()
    return S.fine(fine, detail=True)


@router.post("/fines/{fine_id}/waive")
def waive(fine_id: int, body: WaiverIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    """A librarian *is* the human approver; a reason is mandatory and audited."""
    fine = circulation.waive_fine(db, fine_id, body.amount, body.reason, user)
    db.commit()
    return S.fine(fine, detail=True)


@router.post("/fines/{fine_id}/waiver-request", status_code=201)
def request_waiver(fine_id: int, body: WaiverRequestIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise HTTPException(404, "Fine not found")
    own_member_or_staff(user, fine.member_id)
    if fine.balance <= 0:
        raise HTTPException(409, "This fine has no outstanding balance")
    appr = oversight.request_approval(db, "waiver", body.reason, "member" if user.role == "member" else "librarian", user.name, user=user,
                                      member_id=fine.member_id, fine_id=fine.id, loan_id=fine.loan_id, payload={"amount": fine.balance}, snooze_days=0)
    if appr is None:
        raise HTTPException(409, "A waiver request for this fine is already pending")
    db.commit()
    return S.approval(appr)


@router.get("/approvals")
def list_approvals(
    status: str = Query("pending", pattern="^(pending|approved|rejected|withdrawn|all)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    query = select(Approval).order_by(Approval.created_at.desc())
    if status != "all":
        query = query.where(Approval.status == status)
    if user.role == "member":
        query = query.where(Approval.member_id == user.member_id)
    items = [S.approval(a) for a in db.scalars(query.limit(200)).all()]
    return {"items": items, "total": len(items)}


@router.post("/approvals/{approval_id}/decide")
def decide(approval_id: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    appr = oversight.decide(db, approval_id, body.approve, body.note, user)
    db.commit()
    return S.approval(appr)
