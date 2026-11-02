from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user, own_member_or_staff, staff
from ..models import Notification, User
from ..services import fuzzy
from ..services.agent import NOTIFY_KIND, load_rules, perceive
from ..services.inference import forward_chain
from ..services.priority import NotificationQueue, PriorityInputs, prioritise
from ..services.settings import get_setting, today
from .common import paginate

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    status: str = Query("all", pattern="^(all|sent|read|suppressed|queued|delivered)$"),
    level: str = Query("", pattern="^(|Critical|High|Medium|Low)$"),
    kind: str = Query("", max_length=30),
    member_id: int | None = Query(None, gt=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    query = select(Notification).order_by(Notification.id.desc())
    if user.role == "member":
        query = query.where(Notification.member_id == user.member_id, Notification.status.in_(("sent", "read")))
    elif member_id:
        query = query.where(Notification.member_id == member_id)
    if status == "delivered":
        query = query.where(Notification.status.in_(("sent", "read")))
    elif status != "all":
        query = query.where(Notification.status == status)
    if level:
        query = query.where(Notification.level == level)
    if kind:
        query = query.where(Notification.kind == kind)
    result = paginate(db, query, page, page_size, S.notification)
    if user.role != "member":
        result["counts"] = dict(db.execute(select(Notification.status, func.count()).group_by(Notification.status)).all())
    return result


@router.get("/queue")
def queue_preview(db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    """Dry run: what the agent would push into its heap priority queue right now (no side effects)."""
    on = today(db)
    memory, ctx = perceive(db, on)
    forward_chain(memory, load_rules(db))
    weights = get_setting(db, "priority_weights")
    queue = NotificationQueue()
    for (kind, eid), frame in memory.items():
        for concl, nkind in NOTIFY_KIND.items():
            if not frame.get(concl):
                continue
            if kind == "loan":
                loan = ctx["loans"][eid]
                inputs = PriorityInputs(nkind, frame["days_overdue"], max(frame["days_until_due"], 0), frame["reservation_queue"],
                                        frame["fine_amount"], frame["predicted_risk"], frame["member_late_rate"])
                label, member = loan.copy.book.title, loan.member.name
            elif kind == "member":
                inputs = PriorityInputs(nkind, fine_amount=frame["unpaid_fines"], late_rate=frame["late_rate"])
                label, member = f"₹{frame['unpaid_fines']:g} unpaid", ctx["members"][eid].name
            else:
                r = ctx["reservations"][eid]
                if r.status != "ready":
                    continue
                inputs = PriorityInputs(nkind, days_until_due=max(frame["days_until_expiry"] or 0, 0))
                label, member = r.book.title, r.member.name
            d = prioritise(inputs, weights)
            queue.push({"kind": nkind, "entity": kind, "entity_id": eid, "member": member, "label": label, "score": d.score, "level": d.level,
                        "crisp": d.fuzzy["crisp"], "breakdown": d.breakdown}, d.level, d.score)
    items = queue.snapshot()
    for i, it in enumerate(items, start=1):
        it["rank"] = i
    carried = [S.notification(n) for n in db.scalars(select(Notification).where(Notification.status == "queued")).all()]
    return {"sim_date": on.isoformat(), "items": items, "carried_over": carried, "levels": list(reversed(fuzzy.LEVELS))}


@router.get("/{notification_id}")
def get_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    n = db.get(Notification, notification_id)
    if n is None:
        raise HTTPException(404, "Notification not found")
    own_member_or_staff(user, n.member_id)
    return S.notification(n, detail=True)


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    n = db.get(Notification, notification_id)
    if n is None:
        raise HTTPException(404, "Notification not found")
    own_member_or_staff(user, n.member_id)
    if n.status == "sent":
        n.status = "read"
        n.read_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
    return S.notification(n)


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if user.member_id is None:
        raise HTTPException(400, "Only member accounts have an inbox")
    count = 0
    for n in db.scalars(select(Notification).where(Notification.member_id == user.member_id, Notification.status == "sent")):
        n.status, n.read_at = "read", datetime.now(UTC).replace(tzinfo=None)
        count += 1
    db.commit()
    return {"marked": count}
