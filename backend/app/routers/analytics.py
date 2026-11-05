from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import staff
from ..models import AgentCycle, AgentEvent, Approval, Book, Copy, Fine, Loan, Member, Notification, Payment, Reservation, User, Waiver
from ..services.circulation import OPEN_FINE_STATUSES
from ..services.settings import today

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def overdue_trend(db: Session, on: date, days: int) -> list[dict]:
    start = on - timedelta(days=days - 1)
    loans = db.execute(select(Loan.issued_on, Loan.due_on, Loan.returned_on, Loan.status).where(Loan.due_on < on, (Loan.returned_on.is_(None)) | (Loan.returned_on > start))).all()
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        active = sum(1 for iss, due, ret, st in loans if iss <= d and (ret is None or ret > d))
        overdue = sum(1 for iss, due, ret, st in loans if iss <= d and due < d and (ret is None or ret > d))
        out.append({"date": d.isoformat(), "overdue": overdue, "active_overdue_candidates": active})
    return out


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    on = today(db)
    week_ago = on - timedelta(days=7)
    kpis = {
        "active_loans": db.scalar(select(func.count(Loan.id)).where(Loan.status == "active")) or 0,
        "overdue_loans": db.scalar(select(func.count(Loan.id)).where(Loan.status == "active", Loan.due_on < on)) or 0,
        "due_soon": db.scalar(select(func.count(Loan.id)).where(Loan.status == "active", Loan.due_on >= on, Loan.due_on <= on + timedelta(days=2))) or 0,
        "reservations_waiting": db.scalar(select(func.count(Reservation.id)).where(Reservation.status == "waiting")) or 0,
        "holds_ready": db.scalar(select(func.count(Reservation.id)).where(Reservation.status == "ready")) or 0,
        "unpaid_fines": round(float(db.scalar(select(func.sum(Fine.amount - Fine.amount_paid - Fine.amount_waived)).where(Fine.status.in_(OPEN_FINE_STATUSES))) or 0), 2),
        "collected_7d": round(float(db.scalar(select(func.sum(Payment.amount)).where(Payment.paid_on > week_ago)) or 0), 2),
        "notifications_7d": db.scalar(select(func.count(Notification.id)).where(Notification.sent_on > week_ago)) or 0,
        "suppressed_7d": db.scalar(select(func.count(Notification.id)).where(Notification.status == "suppressed", Notification.created_on > week_ago)) or 0,
        "pending_approvals": db.scalar(select(func.count(Approval.id)).where(Approval.status == "pending")) or 0,
        "members": db.scalar(select(func.count(Member.id))) or 0,
        "titles": db.scalar(select(func.count(Book.id))) or 0,
        "copies": db.scalar(select(func.count(Copy.id))) or 0,
        "high_risk_active": db.scalar(select(func.count(Loan.id)).where(Loan.status == "active", Loan.risk_label == "high")) or 0,
    }
    copy_status = dict(db.execute(select(Copy.status, func.count()).group_by(Copy.status)).all())
    since = on - timedelta(days=13)
    by_level: dict[str, Counter] = defaultdict(Counter)
    for d, level in db.execute(select(Notification.sent_on, Notification.level).where(Notification.sent_on >= since)):
        by_level[d.isoformat()][level] += 1
    notif_series = [{"date": (since + timedelta(days=i)).isoformat(), **{lv: by_level[(since + timedelta(days=i)).isoformat()].get(lv, 0) for lv in ("Critical", "High", "Medium", "Low")}} for i in range(14)]
    last = db.scalar(select(AgentCycle).order_by(AgentCycle.id.desc()))
    recs = [x for x in (last.decisions if last else []) if x.get("type") == "recommendation"]
    events = db.scalars(select(AgentEvent).where(AgentEvent.severity.in_(("warning", "critical", "success"))).order_by(AgentEvent.id.desc()).limit(8)).all()
    return {
        "sim_date": on.isoformat(),
        "kpis": kpis,
        "copy_status": copy_status,
        "overdue_trend": overdue_trend(db, on, 30),
        "notifications_by_level": notif_series,
        "recommendations": recs,
        "recent_events": [S.event(e) for e in events],
        "last_cycle": S.cycle(last) if last else None,
    }


@router.get("/full")
def full(days: int = Query(60, ge=14, le=200), db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    on = today(db)
    start = on - timedelta(days=days - 1)
    # weekly fine collections vs assessed
    weeks: dict[date, dict[str, float]] = defaultdict(lambda: {"collected": 0.0, "waived": 0.0, "assessed": 0.0})
    for d, amt in db.execute(select(Payment.paid_on, Payment.amount).where(Payment.paid_on >= start)):
        weeks[_week_start(d)]["collected"] += amt
    for d, amt in db.execute(select(Waiver.waived_on, Waiver.amount).where(Waiver.waived_on >= start)):
        weeks[_week_start(d)]["waived"] += amt
    for d, amt in db.execute(select(Fine.created_on, Fine.amount).where(Fine.created_on >= start)):
        weeks[_week_start(d)]["assessed"] += amt
    fine_series = [{"week": w.isoformat(), **{k: round(v, 2) for k, v in vals.items()}} for w, vals in sorted(weeks.items())]

    popular = db.execute(
        select(Book.title, Book.category, func.count(Loan.id).label("n")).join(Copy, Copy.book_id == Book.id).join(Loan, Loan.copy_id == Copy.id)
        .group_by(Book.id).order_by(func.count(Loan.id).desc()).limit(10)
    ).all()
    loans_by_cat = dict(db.execute(select(Book.category, func.count(Loan.id)).join(Copy, Copy.book_id == Book.id).join(Loan, Loan.copy_id == Copy.id)
                                   .where(Loan.issued_on >= start).group_by(Book.category)).all())
    res_by_cat = dict(db.execute(select(Book.category, func.count(Reservation.id)).join(Reservation, Reservation.book_id == Book.id)
                                 .where(Reservation.created_on >= start).group_by(Book.category)).all())
    demand = [{"category": c, "loans": loans_by_cat.get(c, 0), "reservations": res_by_cat.get(c, 0)} for c in sorted(set(loans_by_cat) | set(res_by_cat))]

    outcomes: dict[str, Counter] = defaultdict(Counter)
    for kind, status, outcome in db.execute(select(Notification.kind, Notification.status, Notification.outcome)):
        key = "suppressed" if status == "suppressed" else ("queued" if status == "queued" else outcome)
        outcomes[kind][key] += 1
    outcome_series = [{"kind": k, **{x: c.get(x, 0) for x in ("resolved", "pending", "suppressed", "queued")}} for k, c in sorted(outcomes.items())]
    resolve_days = [n.explanation.get("days_to_resolve") for n in db.scalars(select(Notification).where(Notification.outcome == "resolved")) if n.explanation.get("days_to_resolve") is not None]
    channels = dict(db.execute(select(Notification.channel, func.count()).where(Notification.status.in_(("sent", "read"))).group_by(Notification.channel)).all())

    late_by_type = []
    for mtype, total, late in db.execute(
        select(Member.member_type, func.count(Loan.id), func.sum(func.iif(Loan.returned_on > Loan.due_on, 1, 0)))
        .join(Member, Member.id == Loan.member_id).where(Loan.status == "returned").group_by(Member.member_type)
    ):
        late_by_type.append({"member_type": mtype, "loans": total, "late_rate": round((late or 0) / total, 3) if total else 0})

    weekly_loans: Counter = Counter()
    weekly_returns: Counter = Counter()
    for iss, ret in db.execute(select(Loan.issued_on, Loan.returned_on).where(Loan.issued_on >= start)):
        weekly_loans[_week_start(iss)] += 1
    for (ret,) in db.execute(select(Loan.returned_on).where(Loan.returned_on >= start)):
        weekly_returns[_week_start(ret)] += 1
    circ = [{"week": w.isoformat(), "issued": weekly_loans.get(w, 0), "returned": weekly_returns.get(w, 0)} for w in sorted(set(weekly_loans) | set(weekly_returns))]

    risk = Counter(lbl for (lbl,) in db.execute(select(Loan.risk_label).where(Loan.status == "active")) if lbl)
    return {
        "sim_date": on.isoformat(),
        "overdue_trend": overdue_trend(db, on, days),
        "fine_collections": fine_series,
        "popular_books": [{"title": t, "category": c, "loans": n} for t, c, n in popular],
        "demand_by_category": demand,
        "notification_outcomes": outcome_series,
        "avg_days_to_resolve": round(sum(resolve_days) / len(resolve_days), 2) if resolve_days else None,
        "channels": channels,
        "late_rate_by_type": late_by_type,
        "circulation": circ,
        "risk_distribution": dict(risk),
    }
