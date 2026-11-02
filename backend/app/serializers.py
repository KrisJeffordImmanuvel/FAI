"""Convert ORM objects into JSON-friendly dicts for the API."""
from __future__ import annotations

from datetime import date
from typing import Any

from .models import AgentCycle, AgentEvent, Approval, AuditLog, Book, Copy, Fine, Loan, Member, MLModel, Notification, Reservation, Rule, User


def d(v: date | None) -> str | None:
    return v.isoformat() if v else None


def user(u: User) -> dict[str, Any]:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "member_id": u.member_id, "is_active": u.is_active}


def copy(c: Copy) -> dict[str, Any]:
    return {"id": c.id, "barcode": c.barcode, "status": c.status, "shelf": c.shelf, "book_id": c.book_id, "acquired_on": d(c.acquired_on)}


def book(b: Book, counts: dict[str, int] | None = None, waiting: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": b.id,
        "isbn": b.isbn,
        "title": b.title,
        "author": b.author,
        "category": b.category,
        "publisher": b.publisher,
        "year": b.year,
        "price": b.price,
        "description": b.description,
    }
    if counts is not None:
        out["copies_total"] = sum(counts.values())
        out["copies_available"] = counts.get("available", 0)
        out["copy_status"] = counts
    if waiting is not None:
        out["waiting"] = waiting
    return out


def member(m: Member, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "id": m.id,
        "code": m.code,
        "name": m.name,
        "email": m.email,
        "phone": m.phone,
        "member_type": m.member_type,
        "department": m.department,
        "joined_on": d(m.joined_on),
        "status": m.status,
        "restriction_reason": m.restriction_reason,
        "notify_pref": m.notify_pref,
    }
    if stats is not None:
        out["stats"] = stats
    return out


def loan(lo: Loan, today: date | None = None, include_risk: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": lo.id,
        "copy_id": lo.copy_id,
        "barcode": lo.copy.barcode,
        "book_id": lo.copy.book_id,
        "title": lo.copy.book.title,
        "author": lo.copy.book.author,
        "category": lo.copy.book.category,
        "member_id": lo.member_id,
        "member_name": lo.member.name,
        "member_code": lo.member.code,
        "member_type": lo.member.member_type,
        "issued_on": d(lo.issued_on),
        "due_on": d(lo.due_on),
        "returned_on": d(lo.returned_on),
        "renewals": lo.renewals,
        "status": lo.status,
        "fine_id": lo.fine.id if lo.fine else None,
        "fine_amount": lo.fine.amount if lo.fine else 0.0,
        "fine_balance": lo.fine.balance if lo.fine else 0.0,
    }
    if today is not None and lo.status == "active":
        out["days_overdue"] = max((today - lo.due_on).days, 0)
        out["days_until_due"] = (lo.due_on - today).days
    elif lo.returned_on:
        out["days_late"] = max((lo.returned_on - lo.due_on).days, 0)
    if include_risk:
        out["risk_score"] = lo.risk_score
        out["risk_label"] = lo.risk_label
    return out


def reservation(r: Reservation, position: int | None = None) -> dict[str, Any]:
    return {
        "id": r.id,
        "book_id": r.book_id,
        "title": r.book.title,
        "author": r.book.author,
        "member_id": r.member_id,
        "member_name": r.member.name,
        "member_code": r.member.code,
        "member_type": r.member.member_type,
        "created_on": d(r.created_on),
        "status": r.status,
        "copy_barcode": r.copy.barcode if r.copy else None,
        "ready_on": d(r.ready_on),
        "expires_on": d(r.expires_on),
        "closed_on": d(r.closed_on),
        "position": position,
    }


def fine(f: Fine, detail: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": f.id,
        "loan_id": f.loan_id,
        "member_id": f.member_id,
        "member_name": f.member.name,
        "member_code": f.member.code,
        "title": f.loan.copy.book.title,
        "kind": f.kind,
        "amount": f.amount,
        "amount_paid": f.amount_paid,
        "amount_waived": f.amount_waived,
        "balance": f.balance,
        "status": f.status,
        "created_on": d(f.created_on),
        "last_computed_on": d(f.last_computed_on),
        "due_on": d(f.loan.due_on),
        "returned_on": d(f.loan.returned_on),
        "summary": (f.breakdown or {}).get("summary", ""),
    }
    if detail:
        out["breakdown"] = f.breakdown
        out["payments"] = [{"id": p.id, "amount": p.amount, "method": p.method, "paid_on": d(p.paid_on)} for p in f.payments]
        out["waivers"] = [{"id": w.id, "amount": w.amount, "reason": w.reason, "waived_on": d(w.waived_on)} for w in f.waivers]
    return out


def notification(n: Notification, detail: bool = False) -> dict[str, Any]:
    out = {
        "id": n.id,
        "member_id": n.member_id,
        "member_name": n.member.name,
        "kind": n.kind,
        "loan_id": n.loan_id,
        "reservation_id": n.reservation_id,
        "fine_id": n.fine_id,
        "score": n.score,
        "level": n.level,
        "channel": n.channel,
        "subject": n.subject,
        "body": n.body,
        "status": n.status,
        "suppression_reason": n.suppression_reason,
        "outcome": n.outcome,
        "created_on": d(n.created_on),
        "sent_on": d(n.sent_on),
        "read": n.read_at is not None,
        "cycle_id": n.cycle_id,
        "why": (n.explanation or {}).get("why", ""),
    }
    if detail:
        out["explanation"] = n.explanation
    return out


def approval(a: Approval) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "status": a.status,
        "source": a.source,
        "member_id": a.member_id,
        "member_name": a.member.name if a.member else None,
        "loan_id": a.loan_id,
        "fine_id": a.fine_id,
        "payload": a.payload,
        "reason": a.reason,
        "explanation": a.explanation,
        "requested_by": a.requested_by_label,
        "created_on": d(a.created_on),
        "decided_on": d(a.decided_on),
        "decision_note": a.decision_note,
    }


def event(e: AgentEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "cycle_id": e.cycle_id,
        "sim_date": d(e.sim_date),
        "created_at": e.created_at.isoformat() + "Z",
        "phase": e.phase,
        "kind": e.kind,
        "severity": e.severity,
        "title": e.title,
        "detail": e.detail,
        "data": e.data,
        "member_id": e.member_id,
        "loan_id": e.loan_id,
    }


def cycle(c: AgentCycle, detail: bool = False) -> dict[str, Any]:
    out = {
        "id": c.id,
        "sim_date": d(c.sim_date),
        "mode": c.mode,
        "started_at": c.started_at.isoformat() + "Z",
        "duration_ms": c.duration_ms,
        "summary": c.summary,
        "percepts": c.percepts,
        "firing_count": len(c.firings or []),
        "action_count": len(c.actions or []),
    }
    if detail:
        out["firings"] = c.firings
        out["decisions"] = c.decisions
        out["actions"] = c.actions
    return out


def rule(r: Rule) -> dict[str, Any]:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "description": r.description,
        "entity": r.entity,
        "conditions": r.conditions,
        "conclusion": r.conclusion,
        "salience": r.salience,
        "enabled": r.enabled,
        "updated_at": r.updated_at.isoformat() + "Z" if r.updated_at else None,
    }


def ml_model(m: MLModel) -> dict[str, Any]:
    return {
        "id": m.id,
        "algo": m.algo,
        "version": m.version,
        "trained_at": m.trained_at.isoformat() + "Z",
        "params": m.params,
        "metrics": m.metrics,
        "feature_importance": m.feature_importance,
        "dataset_info": m.dataset_info,
        "is_selected": m.is_selected,
    }


def audit(a: AuditLog) -> dict[str, Any]:
    return {
        "id": a.id,
        "created_at": a.created_at.isoformat() + "Z",
        "sim_date": d(a.sim_date),
        "actor": a.actor_label,
        "action": a.action,
        "entity": a.entity,
        "entity_id": a.entity_id,
        "details": a.details,
    }
