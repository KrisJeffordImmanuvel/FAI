"""One-click guided demo scenario for the viva.

Story: Aarav (student) borrows the only copy of *Artificial Intelligence: A
Modern Approach*; Dr. Meera Iyer reserves it. The book becomes overdue, the
agent raises its priority (due-soon → recall → critical), sends notifications
(with duplicate suppression in between), calculates the fine — skipping a
holiday — processes the return and allocates the copy to the next member.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AgentEvent, Book, Copy, Fine, Holiday, Loan, Member, Notification, Reservation, Setting, User
from . import circulation
from .audit import event
from .settings import today
from .simulation import advance

DEMO_BARCODE = "DEMO-AIMA-01"
DEMO_HOLIDAY_NAME = "Library Foundation Day (demo holiday)"
CAST = {
    "borrower": "member@library.local",
    "reserver": "meera.iyer@college.edu",
    "extra": ["riya.patel@college.edu", "kabir.singh@college.edu"],
}

STEPS = [
    {"title": "Set the scene", "summary": "Aarav borrows the only copy; Dr. Meera Iyer joins the reservation queue."},
    {"title": "Advance 1 day — due-soon reminder", "summary": "The agent perceives the loan is due soon and sends a gentle, low-priority reminder."},
    {"title": "Advance 2 days — the book becomes overdue", "summary": "OVERDUE ∧ IN_DEMAND ⇒ HIGH_RECALL_PRIORITY. A recall goes out; a duplicate due-soon notice is suppressed."},
    {"title": "Demand grows, advance 6 days — fine accrues, priority escalates", "summary": "Two more members queue up. Fuzzy logic moves the recall to Critical, overriding the cooldown; fines accrue (holiday skipped)."},
    {"title": "Aarav returns the book", "summary": "The fine is finalised with an itemised breakdown and the copy is allocated to Dr. Iyer automatically."},
    {"title": "Partial payment and collection", "summary": "Aarav pays half the fine; Dr. Iyer collects her held copy. The agent runs one more calm cycle."},
]


def _state(db: Session) -> dict[str, Any] | None:
    row = db.get(Setting, "demo_state")
    return row.value if row else None


def _save(db: Session, state: dict[str, Any] | None) -> None:
    row = db.get(Setting, "demo_state")
    if row is None:
        db.add(Setting(key="demo_state", value=state))
    else:
        row.value = state
    db.flush()


def _member(db: Session, email: str) -> Member:
    m = db.scalar(select(Member).where(Member.email == email))
    if m is None:
        u = db.scalar(select(User).where(User.email == email))
        m = u.member if u else None
    if m is None:
        raise circulation.DomainError(f"Demo member {email} is missing — reset the simulation to reseed.", 500)
    return m


def get_demo(db: Session) -> dict[str, Any]:
    state = _state(db)
    return {"steps": STEPS, "state": state, "next_step": (state or {}).get("step", -1) + 1 if state else 0}


def _max_event_id(db: Session) -> int:
    return db.scalar(select(func.max(AgentEvent.id))) or 0


def _events_since(db: Session, after: int) -> list[int]:
    return list(db.scalars(select(AgentEvent.id).where(AgentEvent.id > after).order_by(AgentEvent.id)))


def start(db: Session, librarian: User) -> dict[str, Any]:
    """Reset the demo entities and run step 0."""
    on = today(db)
    copy = db.scalar(select(Copy).where(Copy.barcode == DEMO_BARCODE))
    if copy is None:
        raise circulation.DomainError("Demo copy missing — reset the simulation to reseed.", 500)
    book = db.get(Book, copy.book_id)
    assert book is not None
    admin = db.scalar(select(User).where(User.role == "admin")) or librarian

    # --- clean up any earlier run
    for res in db.scalars(select(Reservation).where(Reservation.book_id == book.id, Reservation.status.in_(("waiting", "ready")))):
        res.status, res.closed_on = "cancelled", on
    for loan in db.scalars(select(Loan).where(Loan.copy_id == copy.id, Loan.status == "active")):
        loan.status, loan.returned_on = "returned", on
        if loan.fine is not None:
            loan.fine.status = "open"
            if loan.fine.balance > 0:
                circulation.waive_fine(db, loan.fine.id, loan.fine.balance, "Guided demo reset", admin)
    db.flush()
    copy.status = "available"
    borrower = _member(db, CAST["borrower"])
    reserver = _member(db, CAST["reserver"])
    extras = [_member(db, e) for e in CAST["extra"]]
    for m in [borrower, reserver, *extras]:
        m.status, m.restriction_reason = "active", None
    db.flush()

    before = _max_event_id(db)
    event(db, "demo", "demo.start", "Guided demo started", STEPS[0]["summary"], severity="info")
    loan = circulation.issue(db, borrower.id, librarian, copy_id=copy.id, label="Guided demo")
    policy = circulation.get_policy(db, borrower.member_type)
    holidays = circulation.holiday_dates(db)
    loan.issued_on = on - timedelta(days=policy.loan_days - 2)
    loan.due_on = circulation.next_open_day(on + timedelta(days=2), holidays, policy.exclude_sundays)
    res = circulation.reserve(db, reserver.id, book.id, librarian)

    # a demo holiday inside the overdue window shows holiday exclusion in the fine breakdown
    hday = loan.due_on + timedelta(days=4)
    if hday.weekday() == 6:
        hday += timedelta(days=1)
    if db.scalar(select(Holiday).where(Holiday.date == hday)) is None:
        db.add(Holiday(date=hday, name=DEMO_HOLIDAY_NAME))
    db.flush()

    risk = loan.risk_detail or {}
    narrative = [
        f"Aarav Sharma (student) borrows the only copy of “{book.title}” — due {loan.due_on.isoformat()} (2 days from now).",
        f"At checkout the ML model estimated a {risk.get('probability', 0):.0%} late-return risk ({risk.get('label', 'n/a')}). "
        "This is stored as decision support only.",
        f"Dr. Meera Iyer (faculty) reserves the title and is #1 in the queue (reservation #{res.id}).",
        f"{hday.isoformat()} is marked as “{DEMO_HOLIDAY_NAME}” so you can see holiday exclusion in the fine later.",
        f"Student policy: {policy.grace_days}-day grace, slabs {', '.join(_slab_text(s) for s in policy.fine_slabs)}, cap ₹{policy.max_fine:g}.",
    ]
    state = {
        "step": 0,
        "loan_id": loan.id,
        "reservation_id": res.id,
        "book_id": book.id,
        "copy_id": copy.id,
        "borrower_id": borrower.id,
        "reserver_id": reserver.id,
        "extra_ids": [m.id for m in extras],
        "holiday": hday.isoformat(),
        "log": [],
    }
    state["log"].append(_log_entry(db, 0, narrative, before, {"loan_id": loan.id, "reservation_id": res.id}))
    _save(db, state)
    return get_demo(db)


def _slab_text(s: dict[str, Any]) -> str:
    end = s.get("to_day")
    return f"days {s['from_day']}{'-' + str(end) if end else '+'} ₹{s['rate']:g}/day"


def _log_entry(db: Session, step: int, narrative: list[str], before: int, refs: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": step,
        "title": STEPS[step]["title"],
        "sim_date": today(db).isoformat(),
        "narrative": narrative,
        "event_ids": _events_since(db, before),
        "refs": refs,
    }


def _latest_notification(db: Session, member_id: int, kinds: tuple[str, ...], since_id: int = 0, loan_id: int | None = None) -> list[Notification]:
    q = select(Notification).where(Notification.member_id == member_id, Notification.kind.in_(kinds), Notification.id > since_id)
    if loan_id is not None:
        q = q.where(Notification.loan_id == loan_id)
    return list(db.scalars(q.order_by(Notification.id)))


def next_step(db: Session, librarian: User) -> dict[str, Any]:
    state = _state(db)
    if not state:
        raise circulation.DomainError("Start the guided demo first.", 409)
    step = state["step"] + 1
    if step >= len(STEPS):
        raise circulation.DomainError("The demo is complete. Start it again to replay.", 409)
    loan = db.get(Loan, state["loan_id"])
    if loan is None:
        raise circulation.DomainError("Demo loan missing — restart the demo.", 409)
    before = _max_event_id(db)
    last_note = db.scalar(select(func.max(Notification.id))) or 0
    narrative: list[str] = []
    refs: dict[str, Any] = {"loan_id": loan.id}
    event(db, "demo", "demo.step", f"Demo step {step}: {STEPS[step]['title']}", STEPS[step]["summary"])

    if step == 1:
        cycles = advance(db, 1, mode="demo")
        refs["cycle_ids"] = [c.id for c in cycles]
        notes = _latest_notification(db, loan.member_id, ("due_soon", "early_reminder"), last_note, loan.id)
        narrative.append(f"Clock → {today(db).isoformat()}. Perceived: “days_until_due = {(loan.due_on - today(db)).days}”.")
        narrative.append("Rules fired: R06_DUE_SOON (0 ≤ days_until_due ≤ 2) → DUE_SOON, then R10 → NOTIFY_DUE_SOON.")
        for n in notes:
            fz = n.explanation.get("priority", {}).get("fuzzy", {})
            narrative.append(
                f"Notification #{n.id}: {n.level} (utility {n.score}/100, fuzzy crisp {fz.get('crisp')}) via {n.channel} — "
                f"{n.explanation.get('channel', {}).get('reason', '')}"
            )
        refs["notification_ids"] = [n.id for n in notes]
    elif step == 2:
        cycles = advance(db, 2, mode="demo")
        refs["cycle_ids"] = [c.id for c in cycles]
        notes = _latest_notification(db, loan.member_id, ("due_soon", "recall", "overdue"), last_note, loan.id)
        narrative.append(f"Clock → {today(db).isoformat()}. The loan is now {(today(db) - loan.due_on).days} day(s) overdue.")
        narrative.append("Forward chaining: R01 → OVERDUE, R03 → IN_DEMAND (queue = 1), R04: OVERDUE ∧ IN_DEMAND ⇒ HIGH_RECALL_PRIORITY ⇒ R13 NOTIFY_RECALL.")
        narrative.append("R12 (plain overdue notice) did not fire because it requires HIGH_RECALL_PRIORITY to be false — salience ordering at work.")
        for n in notes:
            if n.status == "suppressed":
                narrative.append(f"Suppressed #{n.id} ({n.kind.replace('_', ' ')}): {n.suppression_reason}.")
            else:
                narrative.append(f"Sent #{n.id} {n.kind} — {n.level}, score {n.score}, channel {n.channel}. {n.explanation.get('channel', {}).get('reason', '')}")
        policy = circulation.get_policy(db, loan.member.member_type)
        narrative.append(f"No fine yet: still inside the {policy.grace_days}-day grace period.")
        refs["notification_ids"] = [n.id for n in notes]
    elif step == 3:
        for mid in state["extra_ids"]:
            circulation.reserve(db, mid, state["book_id"], librarian)
        narrative.append("Riya Patel and Kabir Singh also reserve the title → reservation_queue = 3 (fuzzy demand is now partly ‘high’).")
        cycles = advance(db, 6, mode="demo")
        refs["cycle_ids"] = [c.id for c in cycles]
        notes = _latest_notification(db, loan.member_id, ("recall", "overdue"), last_note, loan.id)
        days = (today(db) - loan.due_on).days
        narrative.append(f"Clock → {today(db).isoformat()}: {days} days overdue. R14 fired: recall ignored ≥ 7 days ⇒ ESCALATE_TO_LIBRARIAN.")
        for n in notes:
            if n.status == "sent":
                fz = n.explanation.get("priority", {}).get("fuzzy", {})
                top = sorted(fz.get("activations", []), key=lambda a: -a["strength"])[:2]
                why = "; ".join(f"{a['rule']}: {a['if']} → {a['then']} ({a['strength']})" for a in top)
                narrative.append(f"{n.created_on.isoformat()} sent #{n.id} {n.kind}: {n.level} (score {n.score}). Fuzzy: {why}.")
            else:
                narrative.append(f"{n.created_on.isoformat()} suppressed #{n.id}: {n.suppression_reason}.")
        db.refresh(loan)
        if loan.fine:
            b = loan.fine.breakdown
            narrative.append(f"Fine so far ₹{loan.fine.amount:g}: {b.get('summary', '')}.")
            refs["fine_id"] = loan.fine.id
        refs["notification_ids"] = [n.id for n in notes]
    elif step == 4:
        result = circulation.return_loan(db, loan.id, librarian, label="Guided demo")
        fine: Fine | None = result["fine"]
        narrative.append(f"Aarav returns the book on {today(db).isoformat()}.")
        if fine:
            b = fine.breakdown
            narrative.append(f"Final fine ₹{fine.amount:g} — {b.get('summary', '')}.")
            charged = [ln for ln in b.get("lines", []) if ln["status"] in ("charged", "capped")]
            skipped = [ln for ln in b.get("lines", []) if ln["status"] in ("holiday", "sunday")]
            narrative.append(f"Itemised: {len(charged)} charged day(s); skipped: " + (", ".join(f"{ln['date']} ({ln['status']})" for ln in skipped) or "none") + ".")
            refs["fine_id"] = fine.id
        alloc = result["allocation"]
        if alloc:
            narrative.append(f"Reflex action: the copy is put on hold for {alloc['member_name']} (first in the FIFO queue) until {alloc['expires_on']}.")
            notes = _latest_notification(db, alloc["member_id"], ("reservation_ready",), last_note)
            for n in notes:
                narrative.append(f"Notification #{n.id} to {alloc['member_name']}: {n.level} ({n.score}) via {n.channel} — “{n.subject}”.")
            refs["notification_ids"] = [n.id for n in notes]
        narrative.append("Earlier recall notifications are marked ‘resolved’ (used in the notification-outcome analytics).")
    elif step == 5:
        db.refresh(loan)
        fine = loan.fine
        if fine and fine.balance > 0:
            half = round(fine.balance / 2, 2)
            circulation.record_payment(db, fine.id, half, "upi", librarian)
            narrative.append(f"Aarav pays ₹{half:g} by UPI — partial payment; balance ₹{fine.balance:g} (status: {fine.status.replace('_', ' ')}).")
            refs["fine_id"] = fine.id
        reserver = db.get(Member, state["reserver_id"])
        assert reserver is not None
        new_loan = circulation.issue(db, reserver.id, librarian, book_id=state["book_id"], label="Guided demo")
        narrative.append(f"Dr. Meera Iyer collects the held copy — reservation fulfilled, new loan #{new_loan.id} due {new_loan.due_on.isoformat()}.")
        from .agent import run_cycle

        cyc = run_cycle(db, "demo")
        refs["cycle_ids"] = [cyc.id]
        narrative.append(f"Agent cycle #{cyc.id}: {cyc.summary}")
        narrative.append("Demo complete — open Explainability to inspect any cycle, rule firing, fuzzy membership or score breakdown.")
    state["step"] = step
    state["log"].append(_log_entry(db, step, narrative, before, refs))
    _save(db, dict(state))
    return get_demo(db)
