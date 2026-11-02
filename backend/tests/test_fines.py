"""Deterministic fine engine: grace, slabs, holidays, Sundays, caps, lost books, payments."""
from datetime import date, timedelta

import pytest

from app.services.fines import FinePolicy, Slab, apply_payment, compute_lost_fine, compute_overdue_fine, fine_status, validate_slabs

SLABS = (Slab(1, 7, 2.0), Slab(8, 14, 5.0), Slab(15, None, 10.0))
# 2026-11-02 is a Monday → no Sunday inside short windows unless intended
DUE = date(2026, 11, 2)


def policy(grace=0, cap=1000.0, sundays=False):
    return FinePolicy(SLABS, grace, cap, exclude_sundays=sundays, lost_processing_fee=100.0)


def test_no_fine_on_or_before_due_date():
    assert compute_overdue_fine(DUE, DUE, policy()).total == 0
    assert compute_overdue_fine(DUE, DUE - timedelta(days=3), policy()).total == 0


def test_grace_period_days_are_free():
    r = compute_overdue_fine(DUE, DUE + timedelta(days=2), policy(grace=2))
    assert r.total == 0 and r.grace_days_used == 2
    r = compute_overdue_fine(DUE, DUE + timedelta(days=3), policy(grace=2))
    assert r.total == 2.0  # only day 3 is chargeable (slab 1)
    assert [ln.status for ln in r.lines] == ["grace", "grace", "charged"]


def test_slab_transitions():
    r = compute_overdue_fine(DUE, DUE + timedelta(days=16), policy())
    # 7×2 + 7×5 + 2×10 = 14 + 35 + 20
    assert r.total == 69.0
    rates = [ln.rate for ln in r.lines]
    assert rates[6] == 2.0 and rates[7] == 5.0 and rates[14] == 10.0


def test_holidays_excluded_and_do_not_advance_slab():
    holiday = DUE + timedelta(days=3)
    r = compute_overdue_fine(DUE, DUE + timedelta(days=8), policy(), holidays=[holiday])
    statuses = [ln.status for ln in r.lines]
    assert statuses[2] == "holiday"
    assert r.excluded_days == 1 and r.chargeable_days == 7
    assert r.total == 14.0  # still all slab-1 days because the holiday is skipped


def test_sundays_excluded_when_policy_says_so():
    r = compute_overdue_fine(DUE, DUE + timedelta(days=7), policy(sundays=True))  # includes Sun 8 Nov
    assert any(ln.status == "sunday" for ln in r.lines)
    assert r.total == 12.0


def test_cap_charges_partial_day_then_zero():
    r = compute_overdue_fine(DUE, DUE + timedelta(days=30), policy(cap=40.0))
    assert r.total == 40.0 and r.capped
    capped_lines = [ln for ln in r.lines if ln.status == "capped"]
    assert capped_lines[0].amount == 1.0  # 14 + 5×5 = 39, then only ₹1 of ₹5 fits
    assert all(ln.amount == 0 for ln in capped_lines[1:])
    assert r.lines[-1].cumulative == 40.0


def test_itemised_lines_sum_to_total():
    r = compute_overdue_fine(DUE, DUE + timedelta(days=25), policy(grace=2, cap=120.0, sundays=True), holidays=[DUE + timedelta(days=10)])
    assert round(sum(ln.amount for ln in r.lines), 2) == r.total
    assert r.days_overdue == len(r.lines) == 25


def test_lost_fine_adds_replacement_and_fee():
    r = compute_lost_fine(DUE, DUE + timedelta(days=10), policy(cap=20.0), replacement_cost=650.0)
    assert r.kind == "lost"
    assert r.overdue_total == 20.0 and r.capped
    assert r.total == 20.0 + 650.0 + 100.0


def test_partial_and_full_payments():
    paid, balance = apply_payment(100.0, 0.0, 0.0, 40.0)
    assert (paid, balance) == (40.0, 60.0)
    assert fine_status(100.0, 40.0, 0.0, accruing=False) == "partially_paid"
    paid, balance = apply_payment(100.0, 40.0, 0.0, 60.0)
    assert balance == 0 and fine_status(100.0, paid, 0.0, False) == "paid"


def test_payment_validation():
    with pytest.raises(ValueError):
        apply_payment(50.0, 0.0, 0.0, 0)
    with pytest.raises(ValueError):
        apply_payment(50.0, 20.0, 10.0, 25.0)  # balance is only 20


def test_waived_status():
    assert fine_status(30.0, 0.0, 30.0, False) == "waived"
    assert fine_status(30.0, 10.0, 20.0, False) == "paid"
    assert fine_status(30.0, 0.0, 0.0, True) == "accruing"


def test_slab_validation():
    assert validate_slabs([{"from_day": 1, "to_day": 7, "rate": 2}, {"from_day": 8, "to_day": None, "rate": 5}]) == []
    assert validate_slabs([{"from_day": 2, "to_day": None, "rate": 2}])
    assert validate_slabs([{"from_day": 1, "to_day": 7, "rate": 2}])  # last slab must be open-ended
    assert validate_slabs([{"from_day": 1, "to_day": 7, "rate": -1}, {"from_day": 8, "to_day": None, "rate": 1}])


def test_deterministic():
    a = compute_overdue_fine(DUE, DUE + timedelta(days=20), policy(grace=2, cap=100.0, sundays=True)).to_dict()
    b = compute_overdue_fine(DUE, DUE + timedelta(days=20), policy(grace=2, cap=100.0, sundays=True)).to_dict()
    assert a == b
