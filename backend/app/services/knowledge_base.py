"""Knowledge-base catalogue: fact schema, conclusions, default rules and validation.

The knowledge base itself lives in the ``rules`` table so it can be edited from
the UI. This module describes the vocabulary the rules may use and checks new
rules for safety — including a *fairness taint analysis* that prevents any
penalising conclusion from depending (directly or through a chain of rules)
on the machine-learning prediction.
"""
from __future__ import annotations

from typing import Any

from .inference import OPERATORS

ENTITIES = ("loan", "member", "reservation", "fine")

# Facts the agent perceives for each entity type.
FIELDS: dict[str, dict[str, dict[str, str]]] = {
    "loan": {
        "days_overdue": {"type": "number", "label": "Days past the due date"},
        "days_past_grace": {"type": "number", "label": "Overdue days beyond the grace period"},
        "days_until_due": {"type": "number", "label": "Days until due (negative when overdue)"},
        "reservation_queue": {"type": "number", "label": "Members waiting for this title"},
        "renewals_left": {"type": "number", "label": "Renewals still allowed"},
        "fine_amount": {"type": "number", "label": "Current fine on this loan (₹)"},
        "lost_after_days": {"type": "number", "label": "Policy: overdue days before a book counts as lost"},
        "predicted_risk": {"type": "number", "label": "ML late-return probability (0-1) — decision support only"},
        "member_late_rate": {"type": "number", "label": "Member's historical late-return rate (0-1)"},
        "member_unpaid_fines": {"type": "number", "label": "Member's total unpaid fines (₹)"},
        "member_type": {"type": "text", "label": "student / faculty / staff"},
    },
    "member": {
        "unpaid_fines": {"type": "number", "label": "Total unpaid fines (₹)"},
        "overdue_loans": {"type": "number", "label": "Number of overdue loans"},
        "active_loans": {"type": "number", "label": "Number of active loans"},
        "late_rate": {"type": "number", "label": "Historical late-return rate (0-1)"},
        "status": {"type": "text", "label": "active / restricted / suspended"},
        "fine_notice_threshold": {"type": "number", "label": "Setting: unpaid amount that triggers a fine notice"},
        "restriction_threshold": {"type": "number", "label": "Setting: unpaid amount that suggests restriction"},
    },
    "reservation": {
        "is_ready": {"type": "bool", "label": "A copy is on hold for the member"},
        "is_waiting": {"type": "bool", "label": "Member is still in the queue"},
        "days_waiting": {"type": "number", "label": "Days since the reservation was placed"},
        "days_until_expiry": {"type": "number", "label": "Days left to collect a held copy"},
        "copies_available": {"type": "number", "label": "Free copies on the shelf for this title"},
        "queue_position": {"type": "number", "label": "Position in the reservation queue"},
    },
    "fine": {
        "balance": {"type": "number", "label": "Outstanding balance (₹)"},
        "is_closed_loan": {"type": "bool", "label": "Book already returned"},
        "member_late_rate": {"type": "number", "label": "Member's historical late-return rate (0-1)"},
        "waiver_threshold": {"type": "number", "label": "Setting: max balance for a goodwill waiver suggestion"},
        "has_pending_request": {"type": "bool", "label": "An approval request is already pending"},
    },
}

# Conclusions: intermediate facts and action facts the agent knows how to execute.
CONCLUSIONS: dict[str, dict[str, Any]] = {
    "OVERDUE": {"kind": "intermediate", "label": "Loan is overdue"},
    "FINE_ACCRUING": {"kind": "intermediate", "label": "Fine is accruing (past grace)"},
    "IN_DEMAND": {"kind": "intermediate", "label": "Other members are waiting for the title"},
    "HIGH_RECALL_PRIORITY": {"kind": "intermediate", "label": "Recall the book urgently"},
    "SEVERELY_OVERDUE": {"kind": "intermediate", "label": "Loan is severely overdue"},
    "DUE_SOON": {"kind": "intermediate", "label": "Due within two days"},
    "HIGH_RISK_BORROWER": {"kind": "intermediate", "label": "Model predicts a likely late return (advisory)"},
    "NOTIFY_DUE_SOON": {"kind": "action", "label": "Send a due-soon reminder", "notification": "due_soon"},
    "NOTIFY_EARLY_REMINDER": {"kind": "action", "label": "Send a gentle early reminder", "notification": "early_reminder"},
    "NOTIFY_OVERDUE": {"kind": "action", "label": "Send an overdue notice", "notification": "overdue"},
    "NOTIFY_RECALL": {"kind": "action", "label": "Send a recall notice", "notification": "recall"},
    "NOTIFY_FINE": {"kind": "action", "label": "Send a fine summary", "notification": "fine_notice"},
    "NOTIFY_PICKUP_REMINDER": {"kind": "action", "label": "Remind member to collect a held copy", "notification": "pickup_reminder"},
    "ESCALATE_TO_LIBRARIAN": {"kind": "action", "label": "Recommend personal follow-up by a librarian"},
    "EXPIRE_HOLD": {"kind": "action", "label": "Expire an uncollected hold and pass the copy on"},
    "ALLOCATE_COPY": {"kind": "action", "label": "Allocate a free copy to the queue"},
    "RECOMMEND_MARK_LOST": {"kind": "action", "label": "Ask a librarian to mark the book as lost", "penalising": True, "approval": True},
    "RECOMMEND_RESTRICTION": {"kind": "action", "label": "Ask a librarian to restrict borrowing", "penalising": True, "approval": True},
    "RECOMMEND_WAIVER": {"kind": "action", "label": "Suggest a goodwill waiver to a librarian", "approval": True},
}

PREDICTION_FIELDS = {"predicted_risk"}


def C(field: str, op: str, value: Any = None, value_field: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"field": field, "op": op}
    if value is not None:
        d["value"] = value
    if value_field:
        d["value_field"] = value_field
    return d


DEFAULT_RULES: list[dict[str, Any]] = [
    # ---- loan rules ----
    dict(code="R01_OVERDUE", name="Detect overdue loan", entity="loan", salience=100,
         description="A loan past its due date is overdue.",
         conditions=[C("days_overdue", ">", 0)], conclusion="OVERDUE"),
    dict(code="R02_FINE_ACCRUING", name="Fine accrues after grace", entity="loan", salience=95,
         description="Once the grace period is over the fine starts accruing.",
         conditions=[C("OVERDUE", "is_true"), C("days_past_grace", ">", 0)], conclusion="FINE_ACCRUING"),
    dict(code="R03_IN_DEMAND", name="Title in demand", entity="loan", salience=95,
         description="Someone else is waiting in the reservation queue for this title.",
         conditions=[C("reservation_queue", ">=", 1)], conclusion="IN_DEMAND"),
    dict(code="R04_HIGH_RECALL", name="Overdue AND reserved ⇒ high recall priority", entity="loan", salience=90,
         description="IF a book is overdue AND another member reserved it, THEN assert HIGH_RECALL_PRIORITY.",
         conditions=[C("OVERDUE", "is_true"), C("IN_DEMAND", "is_true")], conclusion="HIGH_RECALL_PRIORITY"),
    dict(code="R05_SEVERE", name="Severely overdue", entity="loan", salience=90,
         description="Two weeks or more overdue.",
         conditions=[C("OVERDUE", "is_true"), C("days_overdue", ">=", 14)], conclusion="SEVERELY_OVERDUE"),
    dict(code="R06_DUE_SOON", name="Due within two days", entity="loan", salience=90,
         description="The due date is today, tomorrow or the day after.",
         conditions=[C("days_until_due", ">=", 0), C("days_until_due", "<=", 2)], conclusion="DUE_SOON"),
    dict(code="R07_RISK_FLAG", name="Advisory high-risk flag", entity="loan", salience=90,
         description="The ML model predicts a likely late return. Advisory only: used for gentle reminders, never penalties.",
         conditions=[C("predicted_risk", ">=", 0.6)], conclusion="HIGH_RISK_BORROWER"),
    dict(code="R10_NOTIFY_DUE_SOON", name="Send due-soon reminder", entity="loan", salience=60,
         description="Remind the member before the book becomes overdue.",
         conditions=[C("DUE_SOON", "is_true")], conclusion="NOTIFY_DUE_SOON"),
    dict(code="R11_EARLY_REMINDER", name="Early reminder for high-risk loans", entity="loan", salience=60,
         description="A friendly nudge 3-4 days early when the model predicts a likely late return.",
         conditions=[C("HIGH_RISK_BORROWER", "is_true"), C("days_until_due", ">=", 3), C("days_until_due", "<=", 4)],
         conclusion="NOTIFY_EARLY_REMINDER"),
    dict(code="R12_NOTIFY_OVERDUE", name="Send overdue notice", entity="loan", salience=55,
         description="Overdue but nobody is waiting: a polite overdue notice.",
         conditions=[C("OVERDUE", "is_true"), C("HIGH_RECALL_PRIORITY", "is_false")], conclusion="NOTIFY_OVERDUE"),
    dict(code="R13_NOTIFY_RECALL", name="Send recall notice", entity="loan", salience=60,
         description="Overdue and reserved: ask the member to return it so the next person can borrow it.",
         conditions=[C("HIGH_RECALL_PRIORITY", "is_true")], conclusion="NOTIFY_RECALL"),
    dict(code="R14_ESCALATE", name="Escalate long recalls", entity="loan", salience=50,
         description="A recall that has been ignored for a week needs a personal call from a librarian.",
         conditions=[C("HIGH_RECALL_PRIORITY", "is_true"), C("days_overdue", ">=", 7)], conclusion="ESCALATE_TO_LIBRARIAN"),
    dict(code="R15_LOST_CANDIDATE", name="Lost-book candidate", entity="loan", salience=40,
         description="Overdue beyond the policy's lost threshold: ask a librarian to review (human approval required).",
         conditions=[C("OVERDUE", "is_true"), C("days_overdue", ">=", value_field="lost_after_days")],
         conclusion="RECOMMEND_MARK_LOST"),
    # ---- member rules ----
    dict(code="R20_FINE_NOTICE", name="Fine summary notice", entity="member", salience=50,
         description="Unpaid fines above the notice threshold trigger a polite summary.",
         conditions=[C("unpaid_fines", ">=", value_field="fine_notice_threshold")], conclusion="NOTIFY_FINE"),
    dict(code="R21_RESTRICT", name="Suggest borrowing restriction", entity="member", salience=40,
         description="Large unpaid fines AND a currently overdue loan: suggest a restriction (librarian decides).",
         conditions=[C("unpaid_fines", ">=", value_field="restriction_threshold"), C("overdue_loans", ">=", 1),
                     C("status", "==", "active")],
         conclusion="RECOMMEND_RESTRICTION"),
    # ---- reservation rules ----
    dict(code="R30_PICKUP_REMINDER", name="Pickup reminder", entity="reservation", salience=50,
         description="A held copy expires within a day.",
         conditions=[C("is_ready", "is_true"), C("days_until_expiry", ">=", 0), C("days_until_expiry", "<=", 1)],
         conclusion="NOTIFY_PICKUP_REMINDER"),
    dict(code="R31_EXPIRE_HOLD", name="Expire uncollected hold", entity="reservation", salience=60,
         description="The pickup window has passed: release the copy to the next member.",
         conditions=[C("is_ready", "is_true"), C("days_until_expiry", "<", 0)], conclusion="EXPIRE_HOLD"),
    dict(code="R32_ALLOCATE", name="Allocate free copy", entity="reservation", salience=55,
         description="The member at the head of the queue gets a copy that is free on the shelf.",
         conditions=[C("is_waiting", "is_true"), C("queue_position", "==", 1), C("copies_available", ">=", 1)],
         conclusion="ALLOCATE_COPY"),
    # ---- fine rules ----
    dict(code="R40_GOODWILL", name="Goodwill waiver suggestion", entity="fine", salience=40,
         description="Small fine on a returned book from a member who is rarely late: suggest a waiver for librarian approval.",
         conditions=[C("is_closed_loan", "is_true"), C("balance", ">", 0), C("balance", "<=", value_field="waiver_threshold"),
                     C("member_late_rate", "<", 0.15), C("has_pending_request", "is_false")],
         conclusion="RECOMMEND_WAIVER"),
]


def schema() -> dict[str, Any]:
    return {"entities": list(ENTITIES), "fields": FIELDS, "operators": OPERATORS, "conclusions": CONCLUSIONS}


def validate_rule(rule: dict[str, Any], all_rules: list[dict[str, Any]]) -> list[str]:
    """Validate a single rule in the context of the whole knowledge base."""
    errors: list[str] = []
    entity = rule.get("entity")
    if entity not in ENTITIES:
        return [f"Unknown entity '{entity}'."]
    code = str(rule.get("code", "")).strip()
    if not code or not code.replace("_", "").isalnum():
        errors.append("Code must be letters, digits and underscores.")
    if not str(rule.get("name", "")).strip():
        errors.append("Name is required.")
    conclusion = rule.get("conclusion")
    if conclusion not in CONCLUSIONS:
        errors.append(f"Unknown conclusion '{conclusion}'.")
    conds = rule.get("conditions") or []
    if not conds:
        errors.append("At least one condition is required.")
    known = set(FIELDS[entity]) | set(CONCLUSIONS)
    for i, c in enumerate(conds, start=1):
        if c.get("field") not in known:
            errors.append(f"Condition {i}: unknown fact '{c.get('field')}' for entity {entity}.")
        if c.get("op") not in OPERATORS:
            errors.append(f"Condition {i}: unknown operator '{c.get('op')}'.")
        if c.get("op") not in ("is_true", "is_false") and c.get("value") is None and not c.get("value_field"):
            errors.append(f"Condition {i}: a value (or another fact to compare with) is required.")
        if c.get("value_field") and c["value_field"] not in FIELDS[entity]:
            errors.append(f"Condition {i}: unknown comparison fact '{c['value_field']}'.")
        if c.get("field") == conclusion:
            errors.append(f"Condition {i}: a rule cannot depend on its own conclusion.")
    if not errors:
        merged = [r for r in all_rules if r.get("code") != code] + [rule]
        errors.extend(fairness_violations(merged))
    return errors


def tainted_facts(rules: list[dict[str, Any]]) -> dict[str, str]:
    """Facts whose truth can depend on the ML prediction → the rule that taints them.

    Computed as a fixpoint over the rule dependency graph.
    """
    tainted: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for r in rules:
            if not r.get("enabled", True):
                continue
            concl = r.get("conclusion")
            if concl in tainted:
                continue
            for c in r.get("conditions") or []:
                if c.get("field") in PREDICTION_FIELDS or c.get("field") in tainted or c.get("value_field") in PREDICTION_FIELDS:
                    tainted[concl] = r.get("code", "?")
                    changed = True
                    break
    return tainted


def fairness_violations(rules: list[dict[str, Any]]) -> list[str]:
    """Penalising conclusions must never depend on the ML prediction (human oversight principle)."""
    tainted = tainted_facts(rules)
    problems = []
    for concl, via in tainted.items():
        if CONCLUSIONS.get(concl, {}).get("penalising"):
            problems.append(
                f"Fairness guard: '{concl}' is a penalising action and cannot depend on the ML prediction "
                f"(dependency through rule {via}). Predictions are decision support only."
            )
    return problems
