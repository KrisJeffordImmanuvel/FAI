"""The library circulation agent: one sense → think → act cycle per simulated day.

PERCEIVE  Build a fact frame for every active loan, open reservation, member
          with activity and open fine (days overdue, queue length, fines,
          history, predicted risk ...). Fines are evaluated deterministically.
THINK     Forward-chain the editable knowledge base over working memory.
          Notification candidates are then scored with the weighted utility
          function and classified with fuzzy logic.
ACT       Persist fines, expire/allocate holds, dispatch notifications via the
          heap priority queue (with anti-spam guard), create approval requests
          for high-impact actions, and log recommendations.

Every cycle's percepts, rule firings, decisions, actions and explanations are
stored in ``agent_cycles`` / ``agent_events`` for the UI.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..models import AgentCycle, Copy, Fine, Loan, Member, Policy, Reservation, Rule
from . import circulation, oversight
from . import fines as fine_engine
from .audit import event
from .inference import Firing, RuleSpec, explain_chain, forward_chain
from .knowledge_base import CONCLUSIONS
from .notifier import Candidate, dispatch
from .priority import PriorityInputs
from .settings import get_setting, today


def load_rules(db: Session) -> list[RuleSpec]:
    return [RuleSpec.from_obj(r) for r in db.scalars(select(Rule).order_by(Rule.salience.desc(), Rule.code))]


def perceive(db: Session, on: date) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[str, Any]]:
    """Sensors: read the environment and build working memory."""
    holidays = circulation.holiday_dates(db)
    policies = {p.member_type: p for p in db.scalars(select(Policy))}
    settings = {k: get_setting(db, k) for k in ("fine_notice_threshold", "restriction_fine_threshold", "waiver_suggestion_max")}

    loans = db.scalars(
        select(Loan).where(Loan.status == "active").options(joinedload(Loan.copy).joinedload(Copy.book), joinedload(Loan.member), joinedload(Loan.fine))
    ).unique().all()
    waiting_by_book: Counter[int] = Counter(
        dict(db.execute(select(Reservation.book_id, func.count()).where(Reservation.status == "waiting").group_by(Reservation.book_id)).all())
    )
    available_by_book: Counter[int] = Counter(
        dict(db.execute(select(Copy.book_id, func.count()).where(Copy.status == "available").group_by(Copy.book_id)).all())
    )
    stats = circulation.member_stats(db, None, on)

    memory: dict[tuple[str, int], dict[str, Any]] = {}
    ctx: dict[str, Any] = {"loans": {}, "fine_results": {}, "reservations": {}, "members": {}, "fines": {}}

    for loan in loans:
        policy = policies[loan.member.member_type]
        result = fine_engine.compute_overdue_fine(loan.due_on, on, circulation.fine_policy(policy), holidays)
        days_overdue = max((on - loan.due_on).days, 0)
        st = stats.get(loan.member_id, {})
        memory[("loan", loan.id)] = {
            "days_overdue": days_overdue,
            "days_past_grace": max(days_overdue - policy.grace_days, 0),
            "days_until_due": (loan.due_on - on).days,
            "reservation_queue": waiting_by_book.get(loan.copy.book_id, 0),
            "renewals_left": max(policy.max_renewals - loan.renewals, 0),
            "fine_amount": result.total,
            "lost_after_days": policy.lost_after_days,
            "predicted_risk": round(loan.risk_score or 0.0, 3),
            "member_late_rate": st.get("late_rate", 0.0),
            "member_unpaid_fines": st.get("unpaid_fines", 0.0),
            "member_type": loan.member.member_type,
        }
        ctx["loans"][loan.id] = loan
        ctx["fine_results"][loan.id] = result

    member_ids = {mid for mid, st in stats.items() if st["active_loans"] or st["unpaid_fines"] > 0}
    members = {m.id: m for m in db.scalars(select(Member).where(Member.id.in_(member_ids)))} if member_ids else {}
    for mid, m in members.items():
        st = stats[mid]
        memory[("member", mid)] = {
            "unpaid_fines": st["unpaid_fines"],
            "overdue_loans": st["overdue_loans"],
            "active_loans": st["active_loans"],
            "late_rate": st["late_rate"],
            "status": m.status,
            "fine_notice_threshold": float(settings["fine_notice_threshold"]),
            "restriction_threshold": float(settings["restriction_fine_threshold"]),
        }
        ctx["members"][mid] = m

    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.status.in_(("waiting", "ready")))
        .options(joinedload(Reservation.book), joinedload(Reservation.member))
        .order_by(Reservation.created_at, Reservation.id)
    ).unique().all()
    position: defaultdict[int, int] = defaultdict(int)
    for r in reservations:
        frame: dict[str, Any] = {
            "is_ready": r.status == "ready",
            "is_waiting": r.status == "waiting",
            "days_waiting": (on - r.created_on).days,
            "copies_available": available_by_book.get(r.book_id, 0),
            "days_until_expiry": (r.expires_on - on).days if r.expires_on else None,
            "queue_position": None,
        }
        if r.status == "waiting":
            position[r.book_id] += 1
            frame["queue_position"] = position[r.book_id]
        memory[("reservation", r.id)] = frame
        ctx["reservations"][r.id] = r

    pending_waiver_fines = set(
        db.scalars(select(oversight.Approval.fine_id).where(oversight.Approval.kind == "waiver", oversight.Approval.status.in_(("pending", "rejected"))))
    )
    open_fines = db.scalars(select(Fine).where(Fine.status.in_(("open", "partially_paid"))).options(joinedload(Fine.loan))).unique().all()
    for f in open_fines:
        memory[("fine", f.id)] = {
            "balance": f.balance,
            "is_closed_loan": f.loan.status == "returned",
            "member_late_rate": stats.get(f.member_id, {}).get("late_rate", 0.0),
            "waiver_threshold": float(settings["waiver_suggestion_max"]),
            "has_pending_request": f.id in pending_waiver_fines,
        }
        ctx["fines"][f.id] = f

    overdue = sum(1 for (k, _), fr in memory.items() if k == "loan" and fr["days_overdue"] > 0)
    summary = {
        "active_loans": len(loans),
        "overdue_loans": overdue,
        "due_within_2_days": sum(1 for (k, _), fr in memory.items() if k == "loan" and 0 <= fr["days_until_due"] <= 2),
        "reservations_waiting": sum(waiting_by_book.values()),
        "holds_ready": sum(1 for r in reservations if r.status == "ready"),
        "members_observed": len(members),
        "unpaid_fines_total": round(sum(st["unpaid_fines"] for st in stats.values()), 2),
        "open_fines": len(open_fines),
        "fact_frames": len(memory),
    }
    ctx["summary"] = summary
    return memory, ctx


def _loan_candidate(kind: str, loan: Loan, frame: dict[str, Any], rules: list[dict[str, Any]], result: fine_engine.FineResult, grace: int) -> Candidate:
    return Candidate(
        member_id=loan.member_id,
        kind=kind,
        dedupe_key=f"{kind}:loan:{loan.id}",
        inputs=PriorityInputs(
            kind=kind,
            days_overdue=frame["days_overdue"],
            days_until_due=max(frame["days_until_due"], 0),
            demand=frame["reservation_queue"],
            fine_amount=result.total,
            risk=frame["predicted_risk"],
            late_rate=frame["member_late_rate"],
        ),
        context={
            "title": loan.copy.book.title,
            "due_on": loan.due_on.isoformat(),
            "days_until_due": frame["days_until_due"],
            "days_overdue": frame["days_overdue"],
            "fine_amount": result.total,
            "demand": frame["reservation_queue"],
            "grace_days": grace,
            "renewals_left": frame["renewals_left"],
        },
        loan_id=loan.id,
        fine_id=loan.fine.id if loan.fine else None,
        rules=rules,
        prediction={k: (loan.risk_detail or {}).get(k) for k in ("probability", "label", "factors", "model", "note")} if loan.risk_detail else None,
    )


NOTIFY_KIND = {name: spec["notification"] for name, spec in CONCLUSIONS.items() if "notification" in spec}


def run_cycle(db: Session, mode: str = "manual") -> AgentCycle:
    t0 = time.perf_counter()
    on = today(db)
    cycle = AgentCycle(sim_date=on, mode=mode)
    db.add(cycle)
    db.flush()
    cid = cycle.id

    # ------------------------------------------------------------ PERCEIVE
    memory, ctx = perceive(db, on)
    s = ctx["summary"]
    event(db, "perceive", "percepts", f"Perceived {s['active_loans']} active loans, {s['overdue_loans']} overdue",
          f"{s['due_within_2_days']} due within 2 days · {s['reservations_waiting']} reservations waiting · "
          f"{s['holds_ready']} holds ready · ₹{s['unpaid_fines_total']:g} unpaid fines across members.",
          data=s, cycle_id=cid)

    # ------------------------------------------------------------ THINK
    rules = load_rules(db)
    trace: list[Firing] = forward_chain(memory, rules)
    by_rule = Counter(f.rule_code for f in trace)
    iterations = max((f.iteration for f in trace), default=0)
    event(db, "think", "inference", f"Forward chaining fired {len(trace)} rule activations in {iterations} iteration(s)",
          ", ".join(f"{code}×{n}" for code, n in by_rule.most_common(8)) or "No rules matched today.",
          data={"by_rule": dict(by_rule), "iterations": iterations}, cycle_id=cid)
    for f in trace:
        if f.asserted == "HIGH_RECALL_PRIORITY":
            loan = ctx["loans"][f.entity_id]
            event(db, "think", "rule.high_recall", f"HIGH_RECALL_PRIORITY asserted for “{loan.copy.book.title}”",
                  f"Rule {f.rule_code}: " + " AND ".join(m["condition"] for m in f.matched) +
                  f" — {memory[('loan', loan.id)]['reservation_queue']} member(s) waiting, {memory[('loan', loan.id)]['days_overdue']} day(s) overdue.",
                  severity="warning", cycle_id=cid, member_id=loan.member_id, loan_id=loan.id, data={"firing": f.to_dict()})

    actions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    # ------------------------------------------------------------ ACT: fines
    holidays = circulation.holiday_dates(db)
    fine_updates = 0
    fine_total = 0.0
    for (kind, eid), frame in memory.items():
        if kind != "loan" or not frame.get("OVERDUE"):
            continue
        loan = ctx["loans"][eid]
        before = loan.fine.amount if loan.fine else 0.0
        fine = circulation.refresh_fine(db, loan, holidays, on)
        if fine is not None and fine.amount != before:
            fine_updates += 1
            fine_total += fine.amount - before
            actions.append({"type": "fine.updated", "loan_id": eid, "fine_id": fine.id, "from": before, "to": fine.amount})
    if fine_updates:
        event(db, "act", "fines", f"Recalculated {fine_updates} accruing fine(s) (+₹{fine_total:g})",
              "Deterministic slab engine with grace period, holidays/Sundays excluded and per-member-type cap. ML is never used here.",
              cycle_id=cid, data={"updated": fine_updates, "delta": round(fine_total, 2)})

    # ------------------------------------------------------------ ACT: reservations
    for (kind, eid), frame in memory.items():
        if kind != "reservation":
            continue
        r = ctx["reservations"][eid]
        if frame.get("EXPIRE_HOLD"):
            nxt = circulation.expire_hold(db, eid, cycle_id=cid)
            event(db, "act", "reservation.expired", f"Hold for {r.member.name} on “{r.book.title}” expired",
                  "Not collected within the pickup window (rule R31). " + (f"Passed to {nxt['member_name']}." if nxt else "Copy returned to the shelf."),
                  severity="info", cycle_id=cid, member_id=r.member_id)
            actions.append({"type": "reservation.expired", "reservation_id": eid, "next": nxt})
    for (kind, eid), frame in memory.items():
        if kind == "reservation" and frame.get("ALLOCATE_COPY"):
            r = ctx["reservations"][eid]
            free = db.scalar(select(Copy).where(Copy.book_id == r.book_id, Copy.status == "available").order_by(Copy.id))
            if free is not None:
                res = circulation.allocate_copy(db, free.id, reason="A free copy was found on the shelf (rule R32)", cycle_id=cid)
                if res:
                    actions.append({"type": "reservation.allocated", **res})

    # ------------------------------------------------------------ ACT: notifications
    candidates: list[Candidate] = []
    for (kind, eid), frame in memory.items():
        for concl, nkind in NOTIFY_KIND.items():
            if not frame.get(concl):
                continue
            chain = explain_chain(frame, concl, trace, kind, eid)
            if kind == "loan":
                loan = ctx["loans"][eid]
                grace = circulation.get_policy(db, loan.member.member_type).grace_days
                candidates.append(_loan_candidate(nkind, loan, frame, chain, ctx["fine_results"][eid], grace))
            elif kind == "member":
                m = ctx["members"][eid]
                candidates.append(Candidate(
                    member_id=eid, kind=nkind, dedupe_key=f"{nkind}:member:{eid}",
                    inputs=PriorityInputs(kind=nkind, fine_amount=frame["unpaid_fines"], late_rate=frame["late_rate"]),
                    context={"unpaid_fines": frame["unpaid_fines"], "member_name": m.name}, rules=chain))
            elif kind == "reservation":
                r = ctx["reservations"][eid]
                if r.status != "ready":
                    continue
                candidates.append(Candidate(
                    member_id=r.member_id, kind=nkind, dedupe_key=f"{nkind}:res:{eid}",
                    inputs=PriorityInputs(kind=nkind, days_until_due=max(frame["days_until_expiry"] or 0, 0), demand=0),
                    context={"title": r.book.title, "expires_on": r.expires_on.isoformat() if r.expires_on else ""},
                    reservation_id=eid, rules=chain))
    result = dispatch(db, candidates, cycle_id=cid)
    actions.append({"type": "notifications", "sent": result["sent"], "suppressed": result["suppressed"], "queued": result["queued"]})
    event(db, "act", "notifications", f"Priority queue processed {len(result['order'])} notification(s): {result['sent']} sent, "
          f"{result['suppressed']} suppressed, {result['queued']} queued",
          "Heap order = (fuzzy level, utility score). Cooldowns, duplicate suppression and daily limits prevent spam.",
          cycle_id=cid, data={"order": result["order"][:50]})
    from ..models import Notification  # local import to avoid cycle at module import

    for o in result["order"]:
        if o.get("status") == "sent" and o["level"] in ("Critical", "High"):
            n = db.get(Notification, o["notification_id"])
            if n is not None:
                event(db, "act", "notification.sent", f"{n.level} {n.kind.replace('_', ' ')} → {n.member.name} via {n.channel.replace('_', '-')}",
                      f"{n.subject}. Score {n.score}/100.", severity="critical" if n.level == "Critical" else "warning",
                      cycle_id=cid, member_id=n.member_id, loan_id=n.loan_id, data={"notification_id": n.id})

    # ------------------------------------------------------------ ACT: approvals & recommendations
    for (kind, eid), frame in memory.items():
        if kind == "loan" and frame.get("RECOMMEND_MARK_LOST"):
            loan = ctx["loans"][eid]
            appr = oversight.request_approval(
                db, "mark_lost", f"“{loan.copy.book.title}” is {frame['days_overdue']} days overdue (policy threshold {frame['lost_after_days']} days).",
                "agent", "Agent", member_id=loan.member_id, loan_id=eid,
                explanation={"rules": explain_chain(frame, "RECOMMEND_MARK_LOST", trace, kind, eid), "facts": _public(frame)})
            if appr:
                actions.append({"type": "approval.requested", "kind": "mark_lost", "approval_id": appr.id})
                event(db, "act", "approval.requested", f"Asked a librarian to review lost book: “{loan.copy.book.title}”",
                      "High-impact action — the agent recommends, a human decides.", severity="warning", cycle_id=cid,
                      member_id=loan.member_id, loan_id=eid, data={"approval_id": appr.id})
        if kind == "loan" and frame.get("ESCALATE_TO_LIBRARIAN"):
            loan = ctx["loans"][eid]
            decisions.append({"type": "recommendation", "loan_id": eid, "text": f"Call {loan.member.name} ({loan.member.phone}) about “{loan.copy.book.title}”"})
            event(db, "act", "recommendation", f"Recommend a personal follow-up with {loan.member.name}",
                  f"Recall for “{loan.copy.book.title}” is {frame['days_overdue']} days overdue with {frame['reservation_queue']} waiting (rule R14).",
                  severity="warning", cycle_id=cid, member_id=loan.member_id, loan_id=eid)
        if kind == "member" and frame.get("RECOMMEND_RESTRICTION"):
            m = ctx["members"][eid]
            appr = oversight.request_approval(
                db, "restrict_member", f"Unpaid fines ₹{frame['unpaid_fines']:g} with {frame['overdue_loans']} overdue loan(s).",
                "agent", "Agent", member_id=eid,
                explanation={"rules": explain_chain(frame, "RECOMMEND_RESTRICTION", trace, kind, eid), "facts": _public(frame),
                             "note": "Based only on recorded fines and overdue loans — never on the ML prediction."})
            if appr:
                actions.append({"type": "approval.requested", "kind": "restrict_member", "approval_id": appr.id})
                event(db, "act", "approval.requested", f"Suggested a borrowing restriction for {m.name} (needs approval)",
                      appr.reason, severity="warning", cycle_id=cid, member_id=eid, data={"approval_id": appr.id})
        if kind == "fine" and frame.get("RECOMMEND_WAIVER"):
            f = ctx["fines"][eid]
            appr = oversight.request_approval(
                db, "waiver", f"Goodwill: small balance ₹{frame['balance']:g} and a good return record (late rate {frame['member_late_rate']:.0%}).",
                "agent", "Agent", member_id=f.member_id, fine_id=eid, loan_id=f.loan_id, payload={"amount": frame["balance"]},
                explanation={"rules": explain_chain(frame, "RECOMMEND_WAIVER", trace, kind, eid), "facts": _public(frame)})
            if appr:
                actions.append({"type": "approval.requested", "kind": "waiver", "approval_id": appr.id})

    # ------------------------------------------------------------ record
    relevant = {key for key in ((f.entity, f.entity_id) for f in trace)}
    for key in sorted(relevant):
        frame = memory[key]
        asserted = [c for c in CONCLUSIONS if frame.get(c)]
        decisions.append({"entity": key[0], "id": key[1], "label": _label(key, ctx), "asserted": asserted, "facts": _public(frame)})
    cycle.percepts = s
    cycle.firings = [f.to_dict() for f in trace]
    cycle.decisions = decisions
    cycle.actions = actions
    cycle.duration_ms = int((time.perf_counter() - t0) * 1000)
    cycle.summary = (
        f"{on.isoformat()}: {s['overdue_loans']} overdue · {len(trace)} rule firings · "
        f"{result['sent']} notifications sent ({result['suppressed']} suppressed) · {fine_updates} fines updated"
    )
    db.flush()
    return cycle


def _public(frame: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in frame.items() if not k.startswith("_") and k not in CONCLUSIONS}


def _label(key: tuple[str, int], ctx: dict[str, Any]) -> str:
    kind, eid = key
    if kind == "loan":
        loan = ctx["loans"][eid]
        return f"Loan #{eid}: “{loan.copy.book.title}” — {loan.member.name}"
    if kind == "member":
        return f"Member {ctx['members'][eid].name}"
    if kind == "reservation":
        r = ctx["reservations"][eid]
        return f"Reservation #{eid}: “{r.book.title}” — {r.member.name}"
    f = ctx["fines"][eid]
    return f"Fine #{eid} — {f.member.name}"


def explain_loan(db: Session, loan_id: int) -> dict[str, Any]:
    """Live, read-only explanation for one loan: facts, rule chain, fuzzy level, score and prediction."""
    from .priority import prioritise

    on = today(db)
    memory, ctx = perceive(db, on)
    key = ("loan", loan_id)
    if key not in memory:
        raise circulation.DomainError("Only active loans can be explained live.", 404)
    frame = memory[key]
    trace = forward_chain({key: frame}, load_rules(db))
    loan = ctx["loans"][loan_id]
    kind = next((NOTIFY_KIND[c] for c in ("NOTIFY_RECALL", "NOTIFY_OVERDUE", "NOTIFY_DUE_SOON", "NOTIFY_EARLY_REMINDER") if frame.get(c)), None)
    inputs = PriorityInputs(
        kind=kind or ("overdue" if frame["days_overdue"] > 0 else "due_soon"),
        days_overdue=frame["days_overdue"], days_until_due=max(frame["days_until_due"], 0), demand=frame["reservation_queue"],
        fine_amount=frame["fine_amount"], risk=frame["predicted_risk"], late_rate=frame["member_late_rate"],
    )
    decision = prioritise(inputs, get_setting(db, "priority_weights"))
    return {
        "loan_id": loan_id,
        "label": _label(key, ctx),
        "sim_date": on.isoformat(),
        "facts": _public(frame),
        "asserted": [c for c in CONCLUSIONS if frame.get(c)],
        "firings": [f.to_dict() for f in trace],
        "notification_kind": kind,
        "priority": decision.to_dict(),
        "inputs": inputs.__dict__ | {"lateness": inputs.lateness},
        "fine": ctx["fine_results"][loan_id].to_dict(),
        "prediction": loan.risk_detail,
    }
