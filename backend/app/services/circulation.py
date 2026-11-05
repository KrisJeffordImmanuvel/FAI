"""Circulation workflows: issue, return, renew, reserve, allocate, lost, payments and waivers.

Concurrency: every request runs in a ``BEGIN IMMEDIATE`` transaction (see
``db.py``), copy status changes use *conditional* UPDATEs (``WHERE status =
expected``), and partial unique indexes forbid two active loans on one copy
or two holds on one copy. A losing concurrent request receives HTTP 409.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from ..models import Approval, Book, Copy, Fine, Holiday, Loan, Member, Payment, Policy, Reservation, User, Waiver
from . import fines as fine_engine
from . import ml
from .audit import audit, event
from .notifier import Candidate, dispatch, resolve_outcomes
from .priority import PriorityInputs
from .settings import today

OPEN_FINE_STATUSES = ("accruing", "open", "partially_paid")


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


# ------------------------------------------------------------------ helpers
def get_policy(db: Session, member_type: str) -> Policy:
    policy = db.scalar(select(Policy).where(Policy.member_type == member_type))
    if policy is None:
        raise DomainError(f"No circulation policy for member type '{member_type}'", 500)
    return policy


def fine_policy(policy: Policy) -> fine_engine.FinePolicy:
    return fine_engine.FinePolicy.from_dict(
        {
            "fine_slabs": policy.fine_slabs,
            "grace_days": policy.grace_days,
            "max_fine": policy.max_fine,
            "exclude_sundays": policy.exclude_sundays,
            "lost_processing_fee": policy.lost_processing_fee,
            "member_type": policy.member_type,
        }
    )


def holiday_dates(db: Session) -> set[date]:
    return set(db.scalars(select(Holiday.date)))


def next_open_day(d: date, holidays: set[date], exclude_sundays: bool) -> date:
    """Due dates never fall on a day the library is closed."""
    for _ in range(30):
        if d in holidays or (exclude_sundays and d.weekday() == 6):
            d += timedelta(days=1)
        else:
            break
    return d


def member_stats(db: Session, member_ids: list[int] | None, on: date) -> dict[int, dict[str, Any]]:
    """Aggregate history per member: prior loans, late rate, unpaid fines, active and overdue loans."""
    q_hist = select(
        Loan.member_id,
        func.count(Loan.id),
        func.sum(case((Loan.returned_on > Loan.due_on, 1), else_=0)),
    ).where(Loan.status.in_(("returned", "lost")))
    q_active = select(
        Loan.member_id, func.count(Loan.id), func.sum(case((Loan.due_on < on, 1), else_=0))
    ).where(Loan.status == "active")
    q_fines = select(
        Fine.member_id, func.sum(Fine.amount - Fine.amount_paid - Fine.amount_waived)
    ).where(Fine.status.in_(OPEN_FINE_STATUSES))
    if member_ids is not None:
        q_hist = q_hist.where(Loan.member_id.in_(member_ids))
        q_active = q_active.where(Loan.member_id.in_(member_ids))
        q_fines = q_fines.where(Fine.member_id.in_(member_ids))
    stats: dict[int, dict[str, Any]] = {}

    def s(mid: int) -> dict[str, Any]:
        return stats.setdefault(mid, {"prior_loans": 0, "late_loans": 0, "late_rate": 0.0, "unpaid_fines": 0.0, "active_loans": 0, "overdue_loans": 0})

    for mid, total, late in db.execute(q_hist.group_by(Loan.member_id)):
        st = s(mid)
        st["prior_loans"], st["late_loans"] = int(total), int(late or 0)
        st["late_rate"] = round((late or 0) / total, 3) if total else 0.0
    for mid, active, overdue in db.execute(q_active.group_by(Loan.member_id)):
        st = s(mid)
        st["active_loans"], st["overdue_loans"] = int(active), int(overdue or 0)
    for mid, unpaid in db.execute(q_fines.group_by(Fine.member_id)):
        s(mid)["unpaid_fines"] = round(float(unpaid or 0), 2)
    for mid in member_ids or []:
        s(mid)
    return stats


def waiting_count(db: Session, book_id: int) -> int:
    return int(db.scalar(select(func.count(Reservation.id)).where(Reservation.book_id == book_id, Reservation.status == "waiting")) or 0)


def checkout_features(db: Session, member: Member, book: Book, on: date, loan_days: int) -> dict[str, Any]:
    st = member_stats(db, [member.id], on)[member.id]
    return {
        "prior_loans": st["prior_loans"],
        "prior_late_rate": st["late_rate"],
        "unpaid_fines": st["unpaid_fines"],
        "active_loans": st["active_loans"],
        "title_demand": waiting_count(db, book.id),
        "loan_days": loan_days,
        "exam_period": ml.is_exam_period(on),
        "weekend_checkout": int(on.weekday() >= 5),
        "member_type": member.member_type,
        "category": book.category,
    }


def _set_copy_status(db: Session, copy_id: int, expected: tuple[str, ...], new: str) -> None:
    """Conditional (compare-and-set) status change; in-session objects are synchronised."""
    db.flush()
    res = db.execute(
        update(Copy).where(Copy.id == copy_id, Copy.status.in_(expected)).values(status=new),
        execution_options={"synchronize_session": "fetch"},
    )
    if res.rowcount != 1:
        raise DomainError("This copy's status changed in another transaction. Please refresh and try again.", 409)


def withdraw_approvals(db: Session, kind: str, note: str, *, loan_id: int | None = None, fine_id: int | None = None) -> int:
    """Close pending approval requests that no longer make sense (e.g. the 'lost' book came back)."""
    q = select(Approval).where(Approval.kind == kind, Approval.status == "pending")
    q = q.where(Approval.loan_id == loan_id) if loan_id is not None else q
    q = q.where(Approval.fine_id == fine_id) if fine_id is not None else q
    n = 0
    for appr in db.scalars(q):
        appr.status, appr.decided_on, appr.decision_note = "withdrawn", today(db), note
        n += 1
    return n


# ------------------------------------------------------------------ fines
def refresh_fine(db: Session, loan: Loan, holidays: set[date] | None = None, on: date | None = None) -> Fine | None:
    """Recompute the deterministic fine for a loan (accruing while active, final once returned)."""
    if loan.status == "lost":
        return loan.fine
    on = on or today(db)
    holidays = holiday_dates(db) if holidays is None else holidays
    policy = get_policy(db, loan.member.member_type)
    until = loan.returned_on or on
    result = fine_engine.compute_overdue_fine(loan.due_on, until, fine_policy(policy), holidays)
    fine = loan.fine
    accruing = loan.status == "active"
    if fine is None:
        if result.total <= 0:
            return None
        fine = Fine(loan_id=loan.id, member_id=loan.member_id, kind="overdue", amount=0.0, amount_paid=0.0, amount_waived=0.0, created_on=on, last_computed_on=on)
        db.add(fine)
        loan.fine = fine
        db.flush()
    fine.amount = max(result.total, fine.amount_paid + fine.amount_waived)
    fine.breakdown = result.to_dict() | {"policy": _policy_snapshot(policy)}
    fine.last_computed_on = on
    fine.status = fine_engine.fine_status(fine.amount, fine.amount_paid, fine.amount_waived, accruing)
    return fine


def _policy_snapshot(policy: Policy) -> dict[str, Any]:
    return {
        "member_type": policy.member_type,
        "grace_days": policy.grace_days,
        "fine_slabs": policy.fine_slabs,
        "max_fine": policy.max_fine,
        "exclude_sundays": policy.exclude_sundays,
        "lost_processing_fee": policy.lost_processing_fee,
    }


def record_payment(db: Session, fine_id: int, amount: float, method: str, actor: User) -> Fine:
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise DomainError("Fine not found", 404)
    try:
        new_paid, _ = fine_engine.apply_payment(fine.amount, fine.amount_paid, fine.amount_waived, amount)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    fine.amount_paid = new_paid
    fine.status = fine_engine.fine_status(fine.amount, fine.amount_paid, fine.amount_waived, fine.status == "accruing")
    db.add(Payment(fine_id=fine.id, amount=round(amount, 2), method=method, paid_on=today(db), recorded_by=actor.id))
    audit(db, "fine.payment", "fine", fine.id, actor, {"amount": amount, "method": method, "balance": fine.balance})
    if fine.balance <= 0:
        resolve_outcomes(db, member_id=fine.member_id, kinds=("fine_notice",))
        withdraw_approvals(db, "waiver", "Fine fully paid — request withdrawn automatically", fine_id=fine.id)
    return fine


def waive_fine(db: Session, fine_id: int, amount: float, reason: str, actor: User) -> Fine:
    fine = db.get(Fine, fine_id)
    if fine is None:
        raise DomainError("Fine not found", 404)
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise DomainError("A waiver needs a recorded reason (at least 5 characters).")
    if amount <= 0 or fine_engine.to_paise(amount) > fine_engine.to_paise(fine.balance):
        raise DomainError(f"Waiver must be between ₹0.01 and the outstanding balance ₹{fine.balance:g}.")
    fine.amount_waived = round(fine.amount_waived + amount, 2)
    fine.status = fine_engine.fine_status(fine.amount, fine.amount_paid, fine.amount_waived, fine.status == "accruing")
    if fine.balance <= 0:
        withdraw_approvals(db, "waiver", "Fine settled by a direct waiver", fine_id=fine.id)
    db.add(Waiver(fine_id=fine.id, amount=round(amount, 2), reason=reason, approved_by=actor.id, waived_on=today(db)))
    audit(db, "fine.waiver", "fine", fine.id, actor, {"amount": amount, "reason": reason})
    return fine


# ------------------------------------------------------------------ loans
def _resolve_copy(db: Session, member: Member, copy_id: int | None, barcode: str | None, book_id: int | None) -> Copy:
    if copy_id:
        copy = db.get(Copy, copy_id)
    elif barcode:
        copy = db.scalar(select(Copy).where(Copy.barcode == barcode.strip().upper()))
    elif book_id:
        held = db.scalar(
            select(Reservation).where(Reservation.book_id == book_id, Reservation.member_id == member.id, Reservation.status == "ready")
        )
        if held and held.copy_id:
            copy = db.get(Copy, held.copy_id)
        else:
            copy = db.scalar(select(Copy).where(Copy.book_id == book_id, Copy.status == "available").order_by(Copy.id))
            if copy is None:
                raise DomainError("No copy of this title is available. The member can join the reservation queue.", 409)
    else:
        raise DomainError("Provide a copy barcode or a book.")
    if copy is None:
        raise DomainError("Copy not found.", 404)
    return copy


def issue(db: Session, member_id: int, actor: User | None, *, copy_id: int | None = None, barcode: str | None = None, book_id: int | None = None, on: date | None = None, label: str | None = None) -> Loan:
    on = on or today(db)
    member = db.get(Member, member_id)
    if member is None:
        raise DomainError("Member not found.", 404)
    if member.status != "active":
        raise DomainError(f"Member is {member.status}: {member.restriction_reason or 'borrowing is not allowed'}.", 403)
    copy = _resolve_copy(db, member, copy_id, barcode, book_id)
    policy = get_policy(db, member.member_type)
    stats = member_stats(db, [member.id], on)[member.id]
    if stats["active_loans"] >= policy.max_loans:
        raise DomainError(f"Borrowing limit reached ({policy.max_loans} books for {policy.label}).")
    dup = db.scalar(
        select(Loan.id).join(Copy, Copy.id == Loan.copy_id).where(Loan.member_id == member.id, Loan.status == "active", Copy.book_id == copy.book_id)
    )
    if dup:
        raise DomainError("Member already has a copy of this title on loan.")

    reservation = None
    if copy.status == "on_hold":
        reservation = db.scalar(select(Reservation).where(Reservation.copy_id == copy.id, Reservation.status == "ready"))
        if reservation is None or reservation.member_id != member.id:
            raise DomainError("This copy is on hold for another member in the reservation queue.", 409)
        _set_copy_status(db, copy.id, ("on_hold",), "on_loan")
    elif copy.status == "available":
        _set_copy_status(db, copy.id, ("available",), "on_loan")
    else:
        raise DomainError(f"Copy {copy.barcode} is not available (status: {copy.status.replace('_', ' ')}).", 409)

    holidays = holiday_dates(db)
    due = next_open_day(on + timedelta(days=policy.loan_days), holidays, policy.exclude_sundays)
    book = db.get(Book, copy.book_id)
    assert book is not None
    features = checkout_features(db, member, book, on, policy.loan_days)
    prediction = ml.predict(db, features)
    loan = Loan(
        copy_id=copy.id,
        member_id=member.id,
        issued_on=on,
        due_on=due,
        status="active",
        issued_by=actor.id if actor else None,
        risk_score=prediction["probability"] if prediction else None,
        risk_label=prediction["label"] if prediction else None,
        risk_detail=(prediction or {}) | {"features": features},
    )
    db.add(loan)
    if reservation is not None:
        reservation.status = "fulfilled"
        reservation.closed_on = on
        resolve_outcomes(db, reservation_id=reservation.id)
    db.flush()
    audit(db, "loan.issue", "loan", loan.id, actor, {"barcode": copy.barcode, "member": member.code, "due_on": due.isoformat()}, actor_label=label)
    return loan


def return_loan(db: Session, loan_id: int, actor: User | None, label: str | None = None) -> dict[str, Any]:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise DomainError("Loan not found.", 404)
    if loan.status != "active":
        raise DomainError(f"This loan is already {loan.status}.", 409)
    on = today(db)
    loan.returned_on = on
    loan.status = "returned"
    _set_copy_status(db, loan.copy_id, ("on_loan",), "available")
    fine = refresh_fine(db, loan, on=on)
    resolve_outcomes(db, loan_id=loan.id)
    withdraw_approvals(db, "mark_lost", "Book was returned — request withdrawn automatically", loan_id=loan.id)
    audit(db, "loan.return", "loan", loan.id, actor, {"fine": fine.amount if fine else 0}, actor_label=label)
    allocation = allocate_copy(db, loan.copy_id, reason=f"Copy returned by {loan.member.name}")
    return {"loan": loan, "fine": fine, "allocation": allocation}


def renew(db: Session, loan_id: int, actor: User) -> Loan:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise DomainError("Loan not found.", 404)
    if loan.status != "active":
        raise DomainError("Only active loans can be renewed.")
    on = today(db)
    member = loan.member
    policy = get_policy(db, member.member_type)
    if member.status != "active":
        raise DomainError(f"Member is {member.status}; renewals are not allowed.", 403)
    if loan.due_on < on:
        raise DomainError("Overdue loans cannot be renewed — please return the book.")
    if loan.renewals >= policy.max_renewals:
        raise DomainError(f"Renewal limit reached ({policy.max_renewals}).")
    if waiting_count(db, loan.copy.book_id) > 0:
        raise DomainError("Another member has reserved this title, so it cannot be renewed.", 409)
    loan.renewals += 1
    loan.due_on = next_open_day(on + timedelta(days=policy.loan_days), holiday_dates(db), policy.exclude_sundays)
    audit(db, "loan.renew", "loan", loan.id, actor, {"new_due_on": loan.due_on.isoformat(), "renewals": loan.renewals})
    resolve_outcomes(db, loan_id=loan.id, kinds=("due_soon", "early_reminder"))
    return loan


def mark_lost(db: Session, loan_id: int, actor: User) -> Loan:
    loan = db.get(Loan, loan_id)
    if loan is None or loan.status != "active":
        raise DomainError("Only an active loan can be marked as lost.", 409)
    on = today(db)
    policy = get_policy(db, loan.member.member_type)
    result = fine_engine.compute_lost_fine(loan.due_on, on, fine_policy(policy), loan.copy.book.price, holiday_dates(db))
    _set_copy_status(db, loan.copy_id, ("on_loan",), "lost")
    loan.status = "lost"
    fine = loan.fine
    if fine is None:
        fine = Fine(loan_id=loan.id, member_id=loan.member_id, amount=0.0, amount_paid=0.0, amount_waived=0.0, created_on=on, last_computed_on=on)
        db.add(fine)
    fine.kind = "lost"
    fine.amount = max(result.total, fine.amount_paid + fine.amount_waived)
    fine.breakdown = result.to_dict() | {"policy": _policy_snapshot(policy)}
    fine.last_computed_on = on
    fine.status = fine_engine.fine_status(fine.amount, fine.amount_paid, fine.amount_waived, False)
    audit(db, "loan.mark_lost", "loan", loan.id, actor, {"fine": fine.amount})
    return loan


# ------------------------------------------------------------------ reservations
def reserve(db: Session, member_id: int, book_id: int, actor: User | None) -> Reservation:
    on = today(db)
    member = db.get(Member, member_id)
    book = db.get(Book, book_id)
    if member is None or book is None:
        raise DomainError("Member or book not found.", 404)
    if member.status != "active":
        raise DomainError(f"Member is {member.status}; reservations are not allowed.", 403)
    policy = get_policy(db, member.member_type)
    has_loan = db.scalar(
        select(Loan.id).join(Copy, Copy.id == Loan.copy_id).where(Loan.member_id == member.id, Loan.status == "active", Copy.book_id == book.id)
    )
    if has_loan:
        raise DomainError("You already have this title on loan.")
    existing = db.scalar(select(Reservation.id).where(Reservation.book_id == book.id, Reservation.member_id == member.id, Reservation.status.in_(("waiting", "ready"))))
    if existing:
        raise DomainError("You already have an open reservation for this title.", 409)
    open_count = db.scalar(select(func.count(Reservation.id)).where(Reservation.member_id == member.id, Reservation.status.in_(("waiting", "ready")))) or 0
    if open_count >= policy.max_reservations:
        raise DomainError(f"Reservation limit reached ({policy.max_reservations}).")
    res = Reservation(book_id=book.id, member_id=member.id, created_on=on, status="waiting")
    db.add(res)
    db.flush()
    audit(db, "reservation.create", "reservation", res.id, actor, {"book": book.title, "member": member.code})
    # A free copy on the shelf is placed on hold immediately for the member.
    free = db.scalar(select(Copy).where(Copy.book_id == book.id, Copy.status == "available").order_by(Copy.id))
    if free is not None and waiting_count(db, book.id) == 1:
        allocate_copy(db, free.id, reason="Copy available on the shelf at reservation time")
        db.refresh(res)
    return res


def cancel_reservation(db: Session, reservation_id: int, actor: User | None, label: str | None = None) -> Reservation:
    res = db.get(Reservation, reservation_id)
    if res is None:
        raise DomainError("Reservation not found.", 404)
    if res.status not in ("waiting", "ready"):
        raise DomainError(f"Reservation is already {res.status}.", 409)
    held_copy = res.copy_id if res.status == "ready" else None
    res.status = "cancelled"
    res.closed_on = today(db)
    db.flush()
    audit(db, "reservation.cancel", "reservation", res.id, actor, {}, actor_label=label)
    if held_copy:
        _set_copy_status(db, held_copy, ("on_hold",), "available")
        allocate_copy(db, held_copy, reason="Previous hold was cancelled")
    return res


def allocate_copy(db: Session, copy_id: int, reason: str, cycle_id: int | None = None) -> dict[str, Any] | None:
    """Give an available copy to the member at the head of the reservation queue (FIFO)."""
    copy = db.get(Copy, copy_id)
    if copy is None or copy.status != "available":
        return None
    nxt = db.scalar(
        select(Reservation)
        .where(Reservation.book_id == copy.book_id, Reservation.status == "waiting")
        .order_by(Reservation.created_at, Reservation.id)
    )
    if nxt is None:
        return None
    on = today(db)
    policy = get_policy(db, nxt.member.member_type)
    _set_copy_status(db, copy.id, ("available",), "on_hold")
    nxt.status = "ready"
    nxt.copy_id = copy.id
    nxt.ready_on = on
    nxt.expires_on = next_open_day(on + timedelta(days=policy.hold_days), holiday_dates(db), policy.exclude_sundays)
    db.flush()
    remaining = waiting_count(db, copy.book_id)
    stats = member_stats(db, [nxt.member_id], on)[nxt.member_id]
    cand = Candidate(
        member_id=nxt.member_id,
        kind="reservation_ready",
        dedupe_key=f"reservation_ready:res:{nxt.id}",
        inputs=PriorityInputs(kind="reservation_ready", days_until_due=(nxt.expires_on - on).days, demand=remaining, late_rate=stats["late_rate"]),
        context={"title": copy.book.title, "expires_on": nxt.expires_on.isoformat()},
        reservation_id=nxt.id,
        rules=[{"rule_code": "REFLEX_ALLOCATE", "rule_name": "Allocate returned copy to queue head (FIFO)", "asserted": "ALLOCATE_COPY",
                "matched": [{"condition": reason, "field": "copy_status", "actual": "available"}]}],
    )
    result = dispatch(db, [cand], cycle_id=cycle_id)
    event(
        db, "act", "reservation.allocated",
        f"Allocated “{copy.book.title}” to {nxt.member.name}",
        f"{reason}. Queue is first-come-first-served; {nxt.member.name} was first in line. Hold until {nxt.expires_on.isoformat()}. "
        f"{remaining} member(s) still waiting.",
        severity="success", cycle_id=cycle_id, member_id=nxt.member_id,
        data={"reservation_id": nxt.id, "copy": copy.barcode, "notification_ids": [o.get("notification_id") for o in result["order"]]},
    )
    audit(db, "reservation.allocate", "reservation", nxt.id, None, {"copy": copy.barcode, "reason": reason})
    return {"reservation_id": nxt.id, "member_id": nxt.member_id, "member_name": nxt.member.name, "copy": copy.barcode, "expires_on": nxt.expires_on.isoformat()}


def expire_hold(db: Session, reservation_id: int, cycle_id: int | None = None) -> dict[str, Any] | None:
    res = db.get(Reservation, reservation_id)
    if res is None or res.status != "ready" or res.copy_id is None:
        return None
    copy_id = res.copy_id
    res.status = "expired"
    res.closed_on = today(db)
    db.flush()
    _set_copy_status(db, copy_id, ("on_hold",), "available")
    audit(db, "reservation.expire", "reservation", reservation_id, None, {})
    return allocate_copy(db, copy_id, reason="Previous hold was not collected in time", cycle_id=cycle_id)


def restrict_member(db: Session, member_id: int, reason: str, actor: User) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise DomainError("Member not found.", 404)
    member.status = "restricted"
    member.restriction_reason = reason
    audit(db, "member.restrict", "member", member.id, actor, {"reason": reason})
    return member
