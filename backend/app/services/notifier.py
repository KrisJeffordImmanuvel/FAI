"""Notification dispatcher: scoring → heap queue → anti-spam guard → channel → persistence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Member, Notification
from . import fuzzy
from .priority import NotificationQueue, PriorityDecision, PriorityInputs, choose_channel, prioritise, render
from .settings import get_setting, today


@dataclass
class Candidate:
    member_id: int
    kind: str
    dedupe_key: str
    inputs: PriorityInputs
    context: dict[str, Any]
    loan_id: int | None = None
    reservation_id: int | None = None
    fine_id: int | None = None
    rules: list[dict[str, Any]] = field(default_factory=list)
    prediction: dict[str, Any] | None = None
    decision: PriorityDecision | None = None


@dataclass
class SentRecord:
    dedupe_key: str
    member_id: int
    level: str
    sent_on: date


class SpamGuard:
    """Cooldowns, duplicate suppression and per-member daily limits (pure logic, no DB)."""

    def __init__(self, history: list[SentRecord], cooldowns: dict[str, int], daily_limit: int, on: date) -> None:
        self.cooldowns = cooldowns
        self.daily_limit = daily_limit
        self.on = on
        self.last: dict[str, SentRecord] = {}
        self.sent_today: dict[int, int] = {}
        self.seen_this_cycle: set[str] = set()
        for rec in sorted(history, key=lambda r: r.sent_on):
            self.last[rec.dedupe_key] = rec
            if rec.sent_on == on:
                self.sent_today[rec.member_id] = self.sent_today.get(rec.member_id, 0) + 1

    def check(self, kind: str, dedupe_key: str, member_id: int, level: str) -> tuple[bool, str, list[str]]:
        checks: list[str] = []
        if dedupe_key in self.seen_this_cycle:
            return False, "Duplicate in the same agent cycle", checks + ["✗ duplicate candidate in this cycle"]
        checks.append("✓ not a duplicate within this cycle")
        prev = self.last.get(dedupe_key)
        cooldown = int(self.cooldowns.get(kind, 2))
        if prev is not None:
            age = (self.on - prev.sent_on).days
            if age < cooldown:
                if fuzzy.LEVEL_RANK[level] > fuzzy.LEVEL_RANK[prev.level]:
                    checks.append(f"✓ cooldown overridden: priority escalated {prev.level} → {level}")
                else:
                    reason = f"Cooldown: same notice sent {age} day(s) ago (cooldown {cooldown} days, level not escalated)"
                    return False, reason, checks + ["✗ " + reason]
            else:
                checks.append(f"✓ last similar notice {age} day(s) ago ≥ cooldown {cooldown}")
        else:
            checks.append("✓ no similar notice sent before")
        count = self.sent_today.get(member_id, 0)
        if count >= self.daily_limit:
            if level == "Critical":
                checks.append(f"✓ daily limit ({self.daily_limit}) reached but Critical notices always go through")
            else:
                reason = f"Daily limit: member already received {count} notification(s) today (limit {self.daily_limit})"
                return False, reason, checks + ["✗ " + reason]
        else:
            checks.append(f"✓ {count}/{self.daily_limit} notifications sent to this member today")
        return True, "", checks

    def record(self, kind: str, dedupe_key: str, member_id: int, level: str) -> None:
        self.seen_this_cycle.add(dedupe_key)
        self.last[dedupe_key] = SentRecord(dedupe_key, member_id, level, self.on)
        self.sent_today[member_id] = self.sent_today.get(member_id, 0) + 1

    def mark_seen(self, dedupe_key: str) -> None:
        self.seen_this_cycle.add(dedupe_key)


def _history(db: Session, on: date, max_cooldown: int) -> list[SentRecord]:
    since = on - timedelta(days=max(max_cooldown, 1))
    rows = db.execute(
        select(Notification.dedupe_key, Notification.member_id, Notification.level, Notification.sent_on).where(
            Notification.status.in_(("sent", "read")), Notification.sent_on.is_not(None), Notification.sent_on >= since
        )
    ).all()
    return [SentRecord(r[0], r[1], r[2], r[3]) for r in rows]


def _why(c: Candidate, decision: PriorityDecision) -> str:
    reasons = {
        "due_soon": "the loan is due within two days",
        "early_reminder": "the model predicts a likely late return, so a gentle early reminder is sent (no penalty)",
        "overdue": "the loan is past its due date",
        "recall": "the loan is overdue and other members are waiting for the title",
        "fine_notice": "unpaid fines exceeded the notice threshold",
        "reservation_ready": "a returned copy was allocated to the member at the head of the queue",
        "pickup_reminder": "the hold on a reserved copy expires within a day",
    }
    return f"Sent because {reasons.get(c.kind, c.kind)}. Priority {decision.level} (utility score {decision.score}/100)."


def dispatch(db: Session, candidates: list[Candidate], cycle_id: int | None = None) -> dict[str, Any]:
    """Score, queue and dispatch candidate notifications. Returns a summary with the processed order."""
    on = today(db)
    weights = get_setting(db, "priority_weights")
    cooldowns = get_setting(db, "cooldown_days")
    guard = SpamGuard(_history(db, on, max(cooldowns.values())), cooldowns, int(get_setting(db, "daily_limit")), on)
    capacity = int(get_setting(db, "dispatch_capacity"))

    queue = NotificationQueue()
    # carry over notifications still queued from an earlier cycle (capacity overflow)
    for old in db.scalars(select(Notification).where(Notification.status == "queued")):
        queue.push(("old", old), old.level, old.score)
    for c in candidates:
        c.decision = prioritise(c.inputs, weights)
        queue.push(("new", c), c.decision.level, c.decision.score)

    members = {m.id: m for m in db.scalars(select(Member).where(Member.id.in_({c.member_id for c in candidates})))}
    order: list[dict[str, Any]] = []
    sent = suppressed = queued = 0
    rank = 0
    while queue:
        tag, item = queue.pop()
        rank += 1
        if tag == "old":
            note: Notification = item
            ok, reason, _checks = guard.check(note.kind, note.dedupe_key, note.member_id, note.level)
            if ok and sent < capacity:
                note.status, note.sent_on = "sent", on
                guard.record(note.kind, note.dedupe_key, note.member_id, note.level)
                sent += 1
            elif not ok:
                note.status, note.suppression_reason = "suppressed", reason
                guard.mark_seen(note.dedupe_key)
                suppressed += 1
            order.append({"rank": rank, "notification_id": note.id, "level": note.level, "score": note.score, "kind": note.kind, "carried_over": True})
            continue

        c: Candidate = item
        d = c.decision
        assert d is not None
        member = members.get(c.member_id)
        pref = member.notify_pref if member else "in_app"
        channel, channel_reason = choose_channel(d.level, pref)
        ok, reason, checks = guard.check(c.kind, c.dedupe_key, c.member_id, d.level)
        if ok and sent >= capacity:
            status, reason = "queued", "Dispatch capacity for this cycle reached — waiting in the priority queue"
        elif ok:
            status = "sent"
        else:
            status = "suppressed"
        ctx = dict(c.context)
        ctx.setdefault("member_name", member.name if member else "Member")
        subject, body = render(c.kind, ctx)
        explanation = {
            "why": _why(c, d) if status != "suppressed" else f"Suppressed: {reason}",
            "rules": c.rules,
            "priority": d.to_dict(),
            "inputs": asdict(c.inputs) | {"lateness": c.inputs.lateness},
            "channel": {"channel": channel, "reason": channel_reason, "preference": pref},
            "anti_spam": checks,
            "prediction": c.prediction,
            "queue_rank": rank,
            "queue_key": "(level rank, utility score) — Critical first, then by score",
        }
        note = Notification(
            member_id=c.member_id,
            kind=c.kind,
            loan_id=c.loan_id,
            reservation_id=c.reservation_id,
            fine_id=c.fine_id,
            score=d.score,
            level=d.level,
            channel=channel,
            subject=subject,
            body=body,
            status=status,
            suppression_reason=reason or None,
            dedupe_key=c.dedupe_key,
            explanation=explanation,
            outcome="pending" if status == "sent" else "n/a",
            created_on=on,
            sent_on=on if status == "sent" else None,
            cycle_id=cycle_id,
        )
        db.add(note)
        if status == "sent":
            guard.record(c.kind, c.dedupe_key, c.member_id, d.level)
            sent += 1
        elif status == "suppressed":
            guard.mark_seen(c.dedupe_key)
            suppressed += 1
        else:
            queued += 1
        order.append({"rank": rank, "level": d.level, "score": d.score, "kind": c.kind, "member_id": c.member_id, "status": status, "note": note})
    db.flush()
    for o in order:
        if "note" in o:
            o["notification_id"] = o.pop("note").id
    return {"sent": sent, "suppressed": suppressed, "queued": queued, "order": order}


def resolve_outcomes(db: Session, *, loan_id: int | None = None, reservation_id: int | None = None, member_id: int | None = None, kinds: tuple[str, ...] | None = None) -> None:
    """Mark sent notifications as resolved when the member acts (returns, collects or pays)."""
    q = select(Notification).where(Notification.outcome == "pending")
    if loan_id is not None:
        q = q.where(Notification.loan_id == loan_id)
    if reservation_id is not None:
        q = q.where(Notification.reservation_id == reservation_id)
    if member_id is not None:
        q = q.where(Notification.member_id == member_id)
    if kinds:
        q = q.where(Notification.kind.in_(kinds))
    on = today(db)
    for n in db.scalars(q):
        n.outcome = "resolved"
        n.explanation = dict(n.explanation) | {"resolved_on": on.isoformat(), "days_to_resolve": (on - (n.sent_on or on)).days}
