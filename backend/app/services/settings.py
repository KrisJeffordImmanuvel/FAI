"""Key/value agent settings with typed defaults, plus the simulated clock."""
from __future__ import annotations

import copy
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..models import Setting

DEFAULT_START_DATE = date(2026, 11, 2)

DEFAULTS: dict[str, Any] = {
    "sim_date": DEFAULT_START_DATE.isoformat(),
    # Weighted utility function for notification priority (weights sum to 100).
    "priority_weights": {
        "urgency": 25,
        "overdue": 20,
        "demand": 20,
        "fine": 10,
        "risk": 15,
        "history": 10,
    },
    # Minimum simulated days before the same notification may be re-sent.
    "cooldown_days": {
        "due_soon": 2,
        "early_reminder": 3,
        "overdue": 3,
        "recall": 2,
        "fine_notice": 5,
        "reservation_ready": 2,
        "pickup_reminder": 1,
    },
    "daily_limit": 3,  # max non-critical notifications per member per simulated day
    "dispatch_capacity": 60,  # max notifications dispatched per agent cycle
    "fine_notice_threshold": 100.0,
    "restriction_fine_threshold": 250.0,
    "waiver_suggestion_max": 20.0,
    "high_risk_threshold": 0.6,
    "background_activity": False,
    "auto_interval_sec": 4,
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(Setting, key)
    if row is None:
        return copy.deepcopy(DEFAULTS[key])
    return row.value


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def all_settings(db: Session) -> dict[str, Any]:
    return {key: get_setting(db, key) for key in DEFAULTS}


def today(db: Session) -> date:
    """The simulated 'current date' used by every agent decision."""
    return date.fromisoformat(get_setting(db, "sim_date"))


def set_today(db: Session, value: date) -> None:
    set_setting(db, "sim_date", value.isoformat())
