"""Deterministic fine calculation engine.

The amount owed is computed *only* from policy data and dates; machine
learning never influences it. All arithmetic is done in integer paise to avoid
floating-point drift, then converted back to rupees for display.

Rules applied for every calendar day after the due date:

1. The first ``grace_days`` overdue days are free (status ``grace``).
2. Library holidays and (optionally) Sundays are not charged (``holiday`` /
   ``sunday``) and do not advance the slab counter.
3. Every other day is a *chargeable day*. Its rate comes from the slab that
   contains the chargeable-day index (e.g. days 1-7 at ₹2, 8-14 at ₹5 ...).
4. The running total is capped at ``max_fine``; the day that reaches the cap is
   charged partially and later days are recorded as ``capped`` at ₹0.

Lost books add the replacement cost and a processing fee on top of the
(capped) overdue fine accrued up to the day the book was declared lost.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any


def to_paise(rupees: float) -> int:
    return int(round(rupees * 100))


def to_rupees(paise: int) -> float:
    return round(paise / 100, 2)


@dataclass(frozen=True)
class Slab:
    from_day: int
    to_day: int | None  # inclusive; None = open-ended
    rate: float  # rupees per chargeable day

    def contains(self, index: int) -> bool:
        return index >= self.from_day and (self.to_day is None or index <= self.to_day)


@dataclass(frozen=True)
class FinePolicy:
    slabs: tuple[Slab, ...]
    grace_days: int
    max_fine: float
    exclude_sundays: bool = True
    lost_processing_fee: float = 0.0
    member_type: str = "student"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> FinePolicy:
        slabs = tuple(
            Slab(int(s["from_day"]), None if s.get("to_day") in (None, "") else int(s["to_day"]), float(s["rate"]))
            for s in data["fine_slabs"]
        )
        return FinePolicy(
            slabs=slabs,
            grace_days=int(data["grace_days"]),
            max_fine=float(data["max_fine"]),
            exclude_sundays=bool(data.get("exclude_sundays", True)),
            lost_processing_fee=float(data.get("lost_processing_fee", 0.0)),
            member_type=str(data.get("member_type", "student")),
        )

    def rate_for(self, chargeable_index: int) -> float:
        for slab in self.slabs:
            if slab.contains(chargeable_index):
                return slab.rate
        return self.slabs[-1].rate if self.slabs else 0.0


@dataclass
class FineLine:
    date: str
    overdue_day: int
    status: str  # grace|holiday|sunday|charged|capped
    chargeable_index: int | None
    rate: float
    amount: float
    cumulative: float
    note: str = ""


@dataclass
class FineResult:
    total: float
    overdue_total: float
    days_overdue: int
    chargeable_days: int
    grace_days_used: int
    excluded_days: int
    capped: bool
    cap: float
    lines: list[FineLine] = field(default_factory=list)
    extra_charges: list[dict[str, Any]] = field(default_factory=list)
    kind: str = "overdue"
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def validate_slabs(slabs: Sequence[dict[str, Any]]) -> list[str]:
    """Return a list of problems with a slab configuration (empty = valid)."""
    errors: list[str] = []
    if not slabs:
        return ["At least one slab is required."]
    expected = 1
    for i, s in enumerate(slabs):
        frm = int(s["from_day"])
        to = s.get("to_day")
        rate = float(s["rate"])
        if frm != expected:
            errors.append(f"Slab {i + 1} must start at day {expected} (found {frm}).")
        if rate < 0:
            errors.append(f"Slab {i + 1} has a negative rate.")
        if to in (None, ""):
            if i != len(slabs) - 1:
                errors.append("Only the last slab may be open-ended.")
            break
        if int(to) < frm:
            errors.append(f"Slab {i + 1} ends before it starts.")
        expected = int(to) + 1
    else:
        if slabs[-1].get("to_day") not in (None, ""):
            errors.append("The last slab must be open-ended (leave 'to day' blank).")
    return errors


def compute_overdue_fine(
    due_on: date,
    until: date,
    policy: FinePolicy,
    holidays: Iterable[date] = (),
) -> FineResult:
    """Itemised overdue fine for a loan due on ``due_on`` evaluated on ``until``."""
    holiday_set = set(holidays)
    days_overdue = max((until - due_on).days, 0)
    cap_paise = to_paise(policy.max_fine)
    cumulative = 0
    chargeable = 0
    grace_used = 0
    excluded = 0
    capped = False
    lines: list[FineLine] = []

    for n in range(1, days_overdue + 1):
        day = due_on + timedelta(days=n)
        iso = day.isoformat()
        if n <= policy.grace_days:
            grace_used += 1
            lines.append(FineLine(iso, n, "grace", None, 0.0, 0.0, to_rupees(cumulative), "Grace period"))
            continue
        if day in holiday_set:
            excluded += 1
            lines.append(FineLine(iso, n, "holiday", None, 0.0, 0.0, to_rupees(cumulative), "Library holiday"))
            continue
        if policy.exclude_sundays and day.weekday() == 6:
            excluded += 1
            lines.append(FineLine(iso, n, "sunday", None, 0.0, 0.0, to_rupees(cumulative), "Library closed (Sunday)"))
            continue
        chargeable += 1
        rate = policy.rate_for(chargeable)
        rate_paise = to_paise(rate)
        if cumulative >= cap_paise:
            capped = True
            lines.append(FineLine(iso, n, "capped", chargeable, rate, 0.0, to_rupees(cumulative), "Maximum fine reached"))
            continue
        charge = min(rate_paise, cap_paise - cumulative)
        cumulative += charge
        note = f"Slab rate ₹{rate:g}/day"
        status = "charged"
        if charge < rate_paise:
            capped = True
            status = "capped"
            note = f"Charged ₹{to_rupees(charge):g} of ₹{rate:g} — cap of ₹{policy.max_fine:g} reached"
        lines.append(FineLine(iso, n, status, chargeable, rate, to_rupees(charge), to_rupees(cumulative), note))

    total = to_rupees(cumulative)
    summary = (
        f"{days_overdue} day(s) overdue: {grace_used} grace, {excluded} excluded (holidays/Sundays), "
        f"{chargeable} chargeable → ₹{total:g}" + (f" (capped at ₹{policy.max_fine:g})" if capped else "")
    )
    return FineResult(
        total=total,
        overdue_total=total,
        days_overdue=days_overdue,
        chargeable_days=chargeable,
        grace_days_used=grace_used,
        excluded_days=excluded,
        capped=capped,
        cap=policy.max_fine,
        lines=lines,
        summary=summary,
    )


def compute_lost_fine(
    due_on: date,
    declared_lost_on: date,
    policy: FinePolicy,
    replacement_cost: float,
    holidays: Iterable[date] = (),
) -> FineResult:
    """Overdue fine up to the lost date + replacement cost + processing fee."""
    result = compute_overdue_fine(due_on, declared_lost_on, policy, holidays)
    extras = [
        {"label": "Replacement cost of the book", "amount": round(replacement_cost, 2)},
        {"label": "Lost-book processing fee", "amount": round(policy.lost_processing_fee, 2)},
    ]
    total_paise = to_paise(result.overdue_total) + sum(to_paise(e["amount"]) for e in extras)
    result.extra_charges = extras
    result.total = to_rupees(total_paise)
    result.kind = "lost"
    result.summary = (
        f"Declared lost: overdue fine ₹{result.overdue_total:g} + replacement ₹{replacement_cost:g} "
        f"+ processing ₹{policy.lost_processing_fee:g} = ₹{result.total:g}"
    )
    return result


def apply_payment(amount_due: float, already_paid: float, already_waived: float, payment: float) -> tuple[float, float]:
    """Validate a payment and return (new_paid_total, new_balance).

    Raises ``ValueError`` for non-positive payments or overpayment.
    """
    balance = to_paise(amount_due) - to_paise(already_paid) - to_paise(already_waived)
    pay = to_paise(payment)
    if pay <= 0:
        raise ValueError("Payment must be greater than zero.")
    if pay > balance:
        raise ValueError(f"Payment exceeds the outstanding balance of ₹{to_rupees(balance):g}.")
    new_paid = to_paise(already_paid) + pay
    return to_rupees(new_paid), to_rupees(balance - pay)


def fine_status(amount: float, paid: float, waived: float, accruing: bool) -> str:
    balance = to_paise(amount) - to_paise(paid) - to_paise(waived)
    if accruing:
        return "accruing"
    if amount <= 0:
        return "paid"
    if balance <= 0:
        return "waived" if to_paise(waived) > 0 and to_paise(paid) == 0 else "paid"
    if to_paise(paid) > 0 or to_paise(waived) > 0:
        return "partially_paid"
    return "open"
