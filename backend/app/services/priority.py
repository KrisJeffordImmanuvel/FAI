"""Notification priority: weighted utility score, fuzzy level, heap queue, channel and templates."""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Any

from . import fuzzy

# Base urgency of each notification type (0-1) used by the utility function.
KIND_URGENCY: dict[str, float] = {
    "recall": 1.0,
    "overdue": 0.8,
    "reservation_ready": 0.7,
    "pickup_reminder": 0.65,
    "fine_notice": 0.5,
    "due_soon": 0.45,
    "early_reminder": 0.3,
}

# Member-level summaries have no due date, so the fuzzy "lateness" input does not apply.
NO_DEADLINE_KINDS = {"fine_notice"}

# Some notification types must never be classified below a minimum level.
KIND_FLOOR: dict[str, str] = {"recall": "High", "reservation_ready": "Medium"}

FACTOR_LABELS = {
    "urgency": "Urgency of the notification type",
    "overdue": "Days overdue (30+ days = max)",
    "demand": "Reservation demand (5+ waiting = max)",
    "fine": "Fine amount (₹500+ = max)",
    "risk": "Predicted late-return risk",
    "history": "Member's past late-return rate",
}


@dataclass
class PriorityInputs:
    kind: str
    days_overdue: float = 0.0
    days_until_due: float = 0.0
    demand: float = 0.0
    fine_amount: float = 0.0
    risk: float = 0.0
    late_rate: float = 0.0

    @property
    def lateness(self) -> float | None:
        """Signed days relative to a deadline; ``None`` when no deadline applies (fine summaries)."""
        if self.kind in NO_DEADLINE_KINDS:
            return None
        return self.days_overdue if self.days_overdue > 0 else -max(self.days_until_due, 0)


def normalise(inputs: PriorityInputs) -> dict[str, float]:
    return {
        "urgency": KIND_URGENCY.get(inputs.kind, 0.4),
        "overdue": min(max(inputs.days_overdue, 0) / 30.0, 1.0),
        "demand": min(max(inputs.demand, 0) / 5.0, 1.0),
        "fine": min(max(inputs.fine_amount, 0) / 500.0, 1.0),
        "risk": min(max(inputs.risk, 0.0), 1.0),
        "history": min(max(inputs.late_rate, 0.0), 1.0),
    }


def utility_score(inputs: PriorityInputs, weights: dict[str, float]) -> tuple[float, list[dict[str, Any]]]:
    """score = Σ weight_k × normalised_k, with weights rescaled to sum to 100."""
    total_w = sum(max(float(w), 0.0) for w in weights.values()) or 1.0
    norm = normalise(inputs)
    raw = {
        "urgency": inputs.kind,
        "overdue": inputs.days_overdue,
        "demand": inputs.demand,
        "fine": inputs.fine_amount,
        "risk": inputs.risk,
        "history": inputs.late_rate,
    }
    breakdown = []
    score = 0.0
    for key, x in norm.items():
        w = max(float(weights.get(key, 0.0)), 0.0) * 100.0 / total_w
        contribution = w * x
        score += contribution
        breakdown.append(
            {
                "factor": key,
                "label": FACTOR_LABELS[key],
                "raw": raw[key],
                "normalised": round(x, 3),
                "weight": round(w, 2),
                "contribution": round(contribution, 2),
            }
        )
    return round(min(score, 100.0), 2), breakdown


@dataclass
class PriorityDecision:
    score: float
    level: str
    breakdown: list[dict[str, Any]]
    fuzzy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "level": self.level, "breakdown": self.breakdown, "fuzzy": self.fuzzy}


def prioritise(inputs: PriorityInputs, weights: dict[str, float]) -> PriorityDecision:
    score, breakdown = utility_score(inputs, weights)
    f = fuzzy.classify(inputs.lateness, inputs.demand, inputs.fine_amount, inputs.risk, floor=KIND_FLOOR.get(inputs.kind))
    return PriorityDecision(score, f.level, breakdown, f.to_dict())


# ---------------------------------------------------------------- heap queue
@dataclass(order=True)
class _Entry:
    sort_key: tuple[int, float, int]
    item: Any = field(compare=False)


class NotificationQueue:
    """Max-priority queue on (fuzzy level, utility score), FIFO for exact ties.

    Python's ``heapq`` is a min-heap, so keys are negated. The level is the
    primary key: every Critical item is served before any High item; the
    utility score breaks ties within a level.
    """

    def __init__(self) -> None:
        self._heap: list[_Entry] = []
        self._counter = itertools.count()

    @staticmethod
    def key(level: str, score: float, seq: int) -> tuple[int, float, int]:
        return (-fuzzy.LEVEL_RANK[level], -float(score), seq)

    def push(self, item: Any, level: str, score: float) -> None:
        heapq.heappush(self._heap, _Entry(self.key(level, score, next(self._counter)), item))

    def pop(self) -> Any:
        return heapq.heappop(self._heap).item

    def peek(self) -> Any:
        return self._heap[0].item

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)

    def snapshot(self) -> list[Any]:
        """Items in the order they would be popped (does not modify the heap)."""
        return [e.item for e in sorted(self._heap)]


# ---------------------------------------------------------------- channel
def choose_channel(level: str, preference: str) -> tuple[str, str]:
    """Pick a delivery channel from priority level and member preference."""
    if level == "Critical":
        if preference == "sms":
            return "sms", "Critical priority → member's preferred urgent channel (SMS)."
        if preference == "email":
            return "sms", "Critical priority → escalated to SMS for immediate attention (also visible in-app)."
        return "email", "Critical priority → member prefers in-app, escalated to email so it is not missed."
    if level == "High":
        if preference in ("email", "sms"):
            return preference, f"High priority → member's preferred channel ({preference})."
        return "in_app", "High priority → member prefers in-app notifications."
    return "in_app", f"{level} priority → in-app only (no external message for routine notices)."


# ---------------------------------------------------------------- templates
def greeting_name(full: str) -> str:
    """'Aarav Sharma' → 'Aarav'; 'Dr. Meera Iyer' → 'Dr. Iyer' (polite form for titled members)."""
    parts = full.split()
    if parts and parts[0].rstrip(".").lower() in {"dr", "prof", "mr", "mrs", "ms"} and len(parts) > 1:
        return f"{parts[0]} {parts[-1]}"
    return parts[0] if parts else "Member"


def render(kind: str, ctx: dict[str, Any]) -> tuple[str, str]:
    """Polite, context-specific message templates."""
    name = greeting_name(ctx.get("member_name", "Member"))
    title = ctx.get("title", "your book")
    due = ctx.get("due_on", "")
    if kind == "due_soon":
        days = ctx.get("days_until_due", 0)
        when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
        extra = " You can renew it from your account if you need more time." if ctx.get("renewals_left", 0) > 0 and not ctx.get("demand") else ""
        return (f"Reminder: “{title}” is due {when}",
                f"Hi {name}, this is a friendly reminder that “{title}” is due {when} ({due}).{extra} Thank you!")
    if kind == "early_reminder":
        return (f"Coming up: “{title}” due on {due}",
                f"Hi {name}, just a heads-up that “{title}” is due on {due}. Planning the return a little early helps "
                f"everyone — and avoids any fines. Have a great week!")
    if kind == "overdue":
        d = ctx.get("days_overdue", 0)
        fine = ctx.get("fine_amount", 0)
        fine_txt = f" A fine of ₹{fine:g} has accrued so far." if fine else f" You are still within the {ctx.get('grace_days', 0)}-day grace period, so no fine yet."
        return (f"“{title}” is {d} day(s) overdue",
                f"Hi {name}, our records show “{title}” was due on {due} and is now {d} day(s) overdue.{fine_txt} "
                f"Please return it at your earliest convenience. If you have already returned it, kindly ignore this message.")
    if kind == "recall":
        d = ctx.get("days_overdue", 0)
        q = ctx.get("demand", 1)
        fine = ctx.get("fine_amount", 0)
        fine_txt = f" The current fine is ₹{fine:g}." if fine else ""
        return (f"Recall: please return “{title}” — {q} member(s) waiting",
                f"Hi {name}, “{title}” is {d} day(s) overdue and {q} other member(s) are waiting for it. "
                f"Could you please return it as soon as possible so they can borrow it?{fine_txt} Thank you for your help!")
    if kind == "fine_notice":
        amt = ctx.get("unpaid_fines", 0)
        return (f"Your library account has ₹{amt:g} in unpaid fines",
                f"Hi {name}, your account currently shows ₹{amt:g} in unpaid fines. You can view an itemised, day-by-day "
                f"breakdown in your account and pay in full or in parts at the circulation desk. "
                f"If you believe a fine is incorrect, you can request a review.")
    if kind == "reservation_ready":
        exp = ctx.get("expires_on", "")
        return (f"Good news: “{title}” is ready for you",
                f"Hi {name}, the copy of “{title}” you reserved is now on hold for you at the circulation desk. "
                f"Please collect it by {exp}; after that it will pass to the next member in the queue.")
    if kind == "pickup_reminder":
        exp = ctx.get("expires_on", "")
        return (f"Last chance to collect “{title}”",
                f"Hi {name}, your reserved copy of “{title}” is waiting for you. The hold ends on {exp} — "
                f"please collect it before then, or cancel the reservation if you no longer need it.")
    return ("Library notification", f"Hi {name}, you have a new library notification.")
