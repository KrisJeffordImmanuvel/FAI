from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user, own_member_or_staff, staff
from ..models import Book, Copy, Loan, Member, Reservation, User
from ..schemas import IssueIn, LostRequestIn, ReserveIn
from ..services import circulation, oversight
from ..services.settings import today
from .common import paginate

router = APIRouter(prefix="/api", tags=["circulation"])


@router.get("/loans")
def list_loans(
    status: str = Query("active", pattern="^(active|returned|lost|overdue|all)$"),
    member_id: int | None = Query(None, gt=0),
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    on = today(db)
    if user.role == "member":
        member_id = user.member_id
    query = select(Loan).join(Copy, Copy.id == Loan.copy_id).join(Book, Book.id == Copy.book_id).join(Member, Member.id == Loan.member_id)
    if status == "overdue":
        query = query.where(Loan.status == "active", Loan.due_on < on)
    elif status != "all":
        query = query.where(Loan.status == status)
    if member_id:
        query = query.where(Loan.member_id == member_id)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Book.title.ilike(like), Member.name.ilike(like), Member.code.ilike(like), Copy.barcode.ilike(like)))
    order = Loan.due_on.asc() if status in ("active", "overdue") else Loan.issued_on.desc()
    return paginate(db, query.order_by(order, Loan.id), page, page_size, lambda lo: S.loan(lo, on, include_risk=user.role != "member"))


@router.get("/loans/{loan_id}")
def get_loan(loan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    own_member_or_staff(user, loan.member_id)
    out = S.loan(loan, today(db), include_risk=user.role != "member")
    if user.role != "member":
        out["risk_detail"] = loan.risk_detail
    out["fine"] = S.fine(loan.fine, detail=True) if loan.fine else None
    return out


@router.post("/loans/issue", status_code=201)
def issue(body: IssueIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    loan = circulation.issue(db, body.member_id, user, barcode=body.barcode, book_id=body.book_id)
    db.commit()
    return S.loan(loan, today(db)) | {"risk_detail": loan.risk_detail}


@router.post("/loans/{loan_id}/return")
def return_loan(loan_id: int, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    result = circulation.return_loan(db, loan_id, user)
    db.commit()
    return {
        "loan": S.loan(result["loan"], today(db)),
        "fine": S.fine(result["fine"], detail=True) if result["fine"] else None,
        "allocation": result["allocation"],
    }


@router.post("/loans/{loan_id}/renew")
def renew(loan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    own_member_or_staff(user, loan.member_id)
    loan = circulation.renew(db, loan_id, user)
    db.commit()
    return S.loan(loan, today(db), include_risk=user.role != "member")


@router.post("/loans/{loan_id}/lost-request", status_code=201)
def request_lost(loan_id: int, body: LostRequestIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    """Marking a book lost is high impact: it always goes through the approval queue."""
    loan = db.get(Loan, loan_id)
    if loan is None or loan.status != "active":
        raise HTTPException(409, "Only active loans can be reported lost")
    appr = oversight.request_approval(db, "mark_lost", body.reason, "librarian", user.name, user=user, member_id=loan.member_id, loan_id=loan.id)
    if appr is None:
        raise HTTPException(409, "A lost-book request for this loan is already pending")
    db.commit()
    return S.approval(appr)


@router.get("/reservations")
def list_reservations(
    status: str = Query("open", pattern="^(open|waiting|ready|fulfilled|cancelled|expired|all)$"),
    member_id: int | None = Query(None, gt=0),
    book_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    if user.role == "member":
        member_id = user.member_id
    query = select(Reservation).order_by(Reservation.book_id, Reservation.created_at, Reservation.id)
    if status == "open":
        query = query.where(Reservation.status.in_(("waiting", "ready")))
    elif status != "all":
        query = query.where(Reservation.status == status)
    if book_id:
        query = query.where(Reservation.book_id == book_id)
    rows = db.scalars(query).all()
    # queue positions are computed over all waiting reservations of each title
    waiting = db.scalars(select(Reservation).where(Reservation.status == "waiting").order_by(Reservation.created_at, Reservation.id)).all()
    pos: dict[int, int] = {}
    counter: dict[int, int] = {}
    for r in waiting:
        counter[r.book_id] = counter.get(r.book_id, 0) + 1
        pos[r.id] = counter[r.book_id]
    items = [S.reservation(r, pos.get(r.id)) for r in rows if not member_id or r.member_id == member_id]
    return {"items": items, "total": len(items)}


@router.post("/reservations", status_code=201)
def reserve(body: ReserveIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    member_id = user.member_id if user.role == "member" else body.member_id
    if not member_id:
        raise HTTPException(422, "member_id is required")
    res = circulation.reserve(db, member_id, body.book_id, user)
    db.commit()
    db.refresh(res)
    return S.reservation(res)


@router.post("/reservations/{reservation_id}/cancel")
def cancel(reservation_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    res = db.get(Reservation, reservation_id)
    if res is None:
        raise HTTPException(404, "Reservation not found")
    own_member_or_staff(user, res.member_id)
    res = circulation.cancel_reservation(db, reservation_id, user)
    db.commit()
    return S.reservation(res)
