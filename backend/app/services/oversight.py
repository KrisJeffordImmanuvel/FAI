"""Human-in-the-loop approvals for high-impact actions (waivers, restrictions, lost books)."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Approval, Fine, Loan, Member, User
from . import circulation
from .audit import audit, event
from .settings import today

KIND_LABELS = {
    "waiver": "Fine waiver",
    "restrict_member": "Restrict borrowing",
    "mark_lost": "Mark book as lost",
}


def request_approval(
    db: Session,
    kind: str,
    reason: str,
    source: str,
    requested_by_label: str,
    *,
    user: User | None = None,
    member_id: int | None = None,
    loan_id: int | None = None,
    fine_id: int | None = None,
    payload: dict[str, Any] | None = None,
    explanation: dict[str, Any] | None = None,
    snooze_days: int = 7,
) -> Approval | None:
    """Create a pending approval unless an equivalent one is pending or was recently rejected."""
    on = today(db)
    q = select(Approval).where(Approval.kind == kind)
    q = q.where(Approval.member_id == member_id) if member_id is not None else q
    q = q.where(Approval.loan_id == loan_id) if loan_id is not None else q
    q = q.where(Approval.fine_id == fine_id) if fine_id is not None else q
    for existing in db.scalars(q):
        if existing.status == "pending":
            return None
        if existing.status == "rejected" and existing.decided_on and on - existing.decided_on < timedelta(days=snooze_days):
            return None  # don't nag a librarian who just said no
        if existing.status == "approved" and kind != "waiver":
            return None
    appr = Approval(
        kind=kind,
        status="pending",
        source=source,
        member_id=member_id,
        loan_id=loan_id,
        fine_id=fine_id,
        payload=payload or {},
        reason=reason,
        explanation=explanation or {},
        requested_by_label=requested_by_label,
        requested_by_user=user.id if user else None,
        created_on=on,
    )
    db.add(appr)
    db.flush()
    audit(db, "approval.request", "approval", appr.id, user, {"kind": kind, "reason": reason}, actor_label=None if user else requested_by_label)
    return appr


def decide(db: Session, approval_id: int, approve: bool, note: str, actor: User) -> Approval:
    appr = db.get(Approval, approval_id)
    if appr is None:
        raise circulation.DomainError("Approval request not found.", 404)
    if appr.status != "pending":
        raise circulation.DomainError(f"This request was already {appr.status}.", 409)
    note = (note or "").strip()
    if approve and appr.kind == "waiver" and len(note) < 5 and len(appr.reason) < 5:
        raise circulation.DomainError("A waiver needs a recorded reason.")
    if not approve and len(note) < 3:
        raise circulation.DomainError("Please record why the request is rejected.")
    on = today(db)
    if approve:
        if appr.kind == "waiver":
            fine = db.get(Fine, appr.fine_id) if appr.fine_id else None
            if fine is None:
                raise circulation.DomainError("Fine no longer exists.", 409)
            amount = float(appr.payload.get("amount") or fine.balance)
            amount = min(amount, fine.balance)
            if amount <= 0:
                raise circulation.DomainError("Nothing left to waive on this fine.", 409)
            reason = f"{appr.reason} — approved by {actor.name}" + (f": {note}" if note else "")
            circulation.waive_fine(db, fine.id, amount, reason, actor)
        elif appr.kind == "restrict_member":
            circulation.restrict_member(db, appr.member_id or 0, note or appr.reason, actor)
        elif appr.kind == "mark_lost":
            loan = db.get(Loan, appr.loan_id) if appr.loan_id else None
            if loan is None:
                raise circulation.DomainError("Loan no longer exists.", 409)
            circulation.mark_lost(db, loan.id, actor)
    appr.status = "approved" if approve else "rejected"
    appr.decided_by = actor.id
    appr.decided_on = on
    appr.decision_note = note or None
    audit(db, f"approval.{appr.status}", "approval", appr.id, actor, {"kind": appr.kind, "note": note})
    member = db.get(Member, appr.member_id) if appr.member_id else None
    event(
        db, "human", f"approval.{appr.status}",
        f"{actor.name} {appr.status} “{KIND_LABELS.get(appr.kind, appr.kind)}”" + (f" for {member.name}" if member else ""),
        note or appr.reason, severity="success" if approve else "info", member_id=appr.member_id, loan_id=appr.loan_id,
        data={"approval_id": appr.id},
    )
    return appr
