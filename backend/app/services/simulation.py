"""Simulated clock and optional background member activity for live demos."""
from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import AgentCycle, Copy, Loan, Member, Reservation
from . import circulation
from .agent import run_cycle
from .audit import event
from .settings import get_setting, set_today, today

DEMO_PREFIX = "DEMO"


def simulate_member_activity(db: Session) -> dict[str, int]:
    """Deterministic (seeded by date) returns, pickups, new loans and reservations."""
    on = today(db)
    rng = random.Random(on.toordinal())
    stats = {"returns": 0, "pickups": 0, "issues": 0, "reservations": 0}

    loans = db.scalars(select(Loan).where(Loan.status == "active").options(joinedload(Loan.member), joinedload(Loan.copy))).all()
    for loan in loans:
        days_left = (loan.due_on - on).days
        risk = loan.risk_score or 0.3
        if days_left > 3:
            p = 0.03
        elif days_left >= 0:
            p = 0.18 * (1.2 - risk)
        else:
            p = 0.10 + 0.25 * (1 - risk)
        if loan.copy.barcode.startswith(DEMO_PREFIX):
            continue  # the guided demo controls its own loan
        if rng.random() < p:
            circulation.return_loan(db, loan.id, None, label="Simulated member activity")
            stats["returns"] += 1

    for res in db.scalars(select(Reservation).where(Reservation.status == "ready")).all():
        if res.copy is not None and res.copy.barcode.startswith(DEMO_PREFIX):
            continue
        if rng.random() < 0.45 and res.member.status == "active":
            try:
                with db.begin_nested():
                    circulation.issue(db, res.member_id, None, book_id=res.book_id, label="Simulated pickup")
                stats["pickups"] += 1
            except circulation.DomainError:
                pass

    members = db.scalars(select(Member).where(Member.status == "active")).all()
    for _ in range(rng.randint(1, 4)):
        member = rng.choice(members)
        copy = db.scalar(select(Copy).where(Copy.status == "available", ~Copy.barcode.startswith(DEMO_PREFIX)).order_by(Copy.id).offset(rng.randint(0, 120)).limit(1))
        if copy is None:
            continue
        try:
            with db.begin_nested():
                circulation.issue(db, member.id, None, copy_id=copy.id, label="Simulated checkout")
            stats["issues"] += 1
        except circulation.DomainError:
            pass

    if rng.random() < 0.5:
        busy = db.scalars(select(Copy.book_id).where(Copy.status == "on_loan", ~Copy.barcode.startswith(DEMO_PREFIX))).all()
        if busy:
            member = rng.choice(members)
            try:
                with db.begin_nested():
                    circulation.reserve(db, member.id, rng.choice(busy), None)
                stats["reservations"] += 1
            except circulation.DomainError:
                pass
    return stats


def advance(db: Session, days: int, run_agent: bool = True, mode: str = "advance") -> list[AgentCycle]:
    if days < 1 or days > 60:
        raise circulation.DomainError("You can advance between 1 and 60 days at a time.")
    cycles: list[AgentCycle] = []
    for _ in range(days):
        new_day = today(db) + timedelta(days=1)
        set_today(db, new_day)
        db.flush()
        detail = ""
        if get_setting(db, "background_activity"):
            act = simulate_member_activity(db)
            detail = f"Simulated activity: {act['returns']} returns, {act['pickups']} pickups, {act['issues']} new loans, {act['reservations']} reservations."
        event(db, "system", "clock", f"Simulated clock advanced to {new_day.strftime('%a %d %b %Y')}", detail)
        if run_agent:
            cycles.append(run_cycle(db, mode))
    return cycles


def status(db: Session) -> dict[str, Any]:
    last = db.scalar(select(AgentCycle).order_by(AgentCycle.id.desc()))
    return {
        "sim_date": today(db).isoformat(),
        "weekday": today(db).strftime("%A"),
        "background_activity": bool(get_setting(db, "background_activity")),
        "auto_interval_sec": int(get_setting(db, "auto_interval_sec")),
        "last_cycle": None if last is None else {"id": last.id, "sim_date": last.sim_date.isoformat(), "summary": last.summary, "duration_ms": last.duration_ms},
    }
