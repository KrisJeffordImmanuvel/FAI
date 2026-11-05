"""Anti-spam guard: cooldowns, escalation override, duplicate suppression, daily limits."""
from datetime import date

from app.services.notifier import SentRecord, SpamGuard

TODAY = date(2026, 11, 10)
COOLDOWNS = {"overdue": 3, "recall": 2, "due_soon": 2}


def guard(history=()):
    return SpamGuard(list(history), COOLDOWNS, daily_limit=2, on=TODAY)


def test_first_notice_allowed():
    ok, reason, checks = guard().check("overdue", "overdue:loan:1", 1, "Medium")
    assert ok and not reason and checks


def test_cooldown_suppresses_repeat():
    g = guard([SentRecord("overdue:loan:1", 1, "Medium", date(2026, 11, 9))])
    ok, reason, _ = g.check("overdue", "overdue:loan:1", 1, "Medium")
    assert not ok and "Cooldown" in reason


def test_cooldown_expires():
    g = guard([SentRecord("overdue:loan:1", 1, "Medium", date(2026, 11, 7))])
    assert g.check("overdue", "overdue:loan:1", 1, "Medium")[0]


def test_escalation_overrides_cooldown():
    g = guard([SentRecord("recall:loan:1", 1, "High", date(2026, 11, 9))])
    ok, _, checks = g.check("recall", "recall:loan:1", 1, "Critical")
    assert ok and any("escalated" in c for c in checks)


def test_duplicate_in_same_cycle_suppressed():
    g = guard()
    assert g.check("due_soon", "due_soon:loan:5", 2, "Low")[0]
    g.record("due_soon", "due_soon:loan:5", 2, "Low")
    ok, reason, _ = g.check("due_soon", "due_soon:loan:5", 2, "Low")
    assert not ok and "Duplicate" in reason


def test_daily_limit_and_critical_bypass():
    g = guard([SentRecord("a", 3, "Low", TODAY), SentRecord("b", 3, "Low", TODAY)])
    ok, reason, _ = g.check("overdue", "overdue:loan:9", 3, "High")
    assert not ok and "Daily limit" in reason
    assert g.check("recall", "recall:loan:9", 3, "Critical")[0]
    # other members are unaffected
    assert g.check("overdue", "overdue:loan:10", 4, "High")[0]
