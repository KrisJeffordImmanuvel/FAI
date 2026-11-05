"""Pydantic request models — the backend half of input validation."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["admin", "librarian", "member"]
MemberType = Literal["student", "faculty", "staff"]
Channel = Literal["in_app", "email", "sms"]
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)


def _strong_password(v: str) -> str:
    if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
        raise ValueError("Password must contain letters and digits")
    return v


class RegisterIn(Strict):
    """Self-service sign-up. Always creates a *member* account — never staff."""

    name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=EMAIL_RE, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    member_type: MemberType = "student"
    department: str = Field(min_length=2, max_length=60)
    phone: str = Field(default="", pattern=r"^(\+?[0-9 ]{8,16})?$")
    notify_pref: Channel = "email"

    @field_validator("password")
    @classmethod
    def strong(cls, v: str) -> str:
        return _strong_password(v)


class ChangePasswordIn(Strict):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong(cls, v: str) -> str:
        return _strong_password(v)


class BookIn(Strict):
    isbn: str = Field(pattern=r"^\d{10}(\d{3})?$", description="ISBN-10 or ISBN-13 (digits only)")
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=60)
    publisher: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1450, le=2100)
    price: float = Field(gt=0, le=100000)
    description: str = Field(default="", max_length=2000)
    copies: int = Field(default=1, ge=0, le=50)


class BookUpdate(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    author: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    publisher: str | None = Field(default=None, min_length=1, max_length=120)
    year: int | None = Field(default=None, ge=1450, le=2100)
    price: float | None = Field(default=None, gt=0, le=100000)
    description: str | None = Field(default=None, max_length=2000)


class CopyIn(Strict):
    count: int = Field(default=1, ge=1, le=20)
    shelf: str = Field(default="NEW-1A", min_length=1, max_length=20)


class CopyStatusIn(Strict):
    status: Literal["available", "maintenance"]


class MemberIn(Strict):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=EMAIL_RE, max_length=120)
    phone: str = Field(pattern=r"^\+?[0-9 ]{8,16}$")
    member_type: MemberType
    department: str = Field(min_length=2, max_length=60)
    notify_pref: Channel = "email"
    create_login: bool = True


class MemberUpdate(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9 ]{8,16}$")
    department: str | None = Field(default=None, min_length=2, max_length=60)
    notify_pref: Channel | None = None
    member_type: MemberType | None = None


class MemberStatusIn(Strict):
    status: Literal["active", "restricted", "suspended"]
    reason: str = Field(default="", max_length=255)


class PreferencesIn(Strict):
    notify_pref: Channel


class IssueIn(Strict):
    member_id: int = Field(gt=0)
    barcode: str | None = Field(default=None, max_length=30)
    book_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def one_target(self) -> IssueIn:
        if not self.barcode and not self.book_id:
            raise ValueError("Provide a copy barcode or a book id")
        return self


class ReserveIn(Strict):
    book_id: int = Field(gt=0)
    member_id: int | None = Field(default=None, gt=0)


class PaymentIn(Strict):
    amount: float = Field(gt=0, le=100000)
    method: Literal["cash", "upi", "card"] = "cash"


class WaiverIn(Strict):
    amount: float = Field(gt=0, le=100000)
    reason: str = Field(min_length=5, max_length=500)


class WaiverRequestIn(Strict):
    reason: str = Field(min_length=10, max_length=500)


class LostRequestIn(Strict):
    reason: str = Field(min_length=5, max_length=500)


class DecisionIn(Strict):
    approve: bool
    note: str = Field(default="", max_length=500)


class FinePreviewIn(Strict):
    member_type: MemberType
    due_on: date
    returned_on: date
    lost: bool = False
    replacement_cost: float = Field(default=0, ge=0, le=100000)


class AdvanceIn(Strict):
    days: int = Field(ge=1, le=60)
    run_agent: bool = True


class RunIn(Strict):
    mode: Literal["manual", "auto"] = "manual"


class ConditionIn(Strict):
    field: str = Field(min_length=1, max_length=40)
    op: Literal["==", "!=", ">", ">=", "<", "<=", "in", "is_true", "is_false"]
    value: Any = None
    value_field: str | None = None


class RuleIn(Strict):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=500)
    entity: Literal["loan", "member", "reservation", "fine"]
    conditions: list[ConditionIn] = Field(min_length=1, max_length=8)
    conclusion: str = Field(min_length=2, max_length=40)
    salience: int = Field(default=50, ge=0, le=1000)
    enabled: bool = True


class RuleTestIn(Strict):
    entity: Literal["loan", "member", "reservation", "fine"]
    facts: dict[str, Any]


class RetrainIn(Strict):
    n_samples: int = Field(default=4000, ge=500, le=20000)
    seed: int = Field(default=42, ge=0, le=10_000)
    include_history: bool = True


class PredictIn(Strict):
    prior_loans: int = Field(ge=0, le=500)
    prior_late_rate: float = Field(ge=0, le=1)
    unpaid_fines: float = Field(ge=0, le=100000)
    active_loans: int = Field(ge=0, le=20)
    title_demand: int = Field(ge=0, le=20)
    loan_days: int = Field(ge=1, le=120)
    exam_period: int = Field(ge=0, le=1)
    weekend_checkout: int = Field(ge=0, le=1)
    member_type: MemberType
    category: str


class UserIn(Strict):
    email: str = Field(pattern=EMAIL_RE, max_length=120)
    name: str = Field(min_length=2, max_length=120)
    role: Literal["admin", "librarian"]
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def strong(cls, v: str) -> str:
        return _strong_password(v)


class UserUpdate(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class SlabIn(Strict):
    from_day: int = Field(ge=1, le=365)
    to_day: int | None = Field(default=None, ge=1, le=365)
    rate: float = Field(ge=0, le=1000)


class PolicyIn(Strict):
    label: str = Field(min_length=2, max_length=60)
    max_loans: int = Field(ge=1, le=50)
    loan_days: int = Field(ge=1, le=120)
    max_renewals: int = Field(ge=0, le=10)
    max_reservations: int = Field(ge=0, le=20)
    grace_days: int = Field(ge=0, le=30)
    fine_slabs: list[SlabIn] = Field(min_length=1, max_length=6)
    max_fine: float = Field(ge=0, le=100000)
    exclude_sundays: bool
    lost_after_days: int = Field(ge=7, le=365)
    lost_processing_fee: float = Field(ge=0, le=10000)
    hold_days: int = Field(ge=1, le=30)


class HolidayIn(Strict):
    date: date
    name: str = Field(min_length=2, max_length=120)


class AgentSettingsIn(Strict):
    priority_weights: dict[str, float] | None = None
    cooldown_days: dict[str, int] | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=20)
    dispatch_capacity: int | None = Field(default=None, ge=1, le=500)
    fine_notice_threshold: float | None = Field(default=None, ge=0, le=100000)
    restriction_fine_threshold: float | None = Field(default=None, ge=0, le=100000)
    waiver_suggestion_max: float | None = Field(default=None, ge=0, le=10000)
    background_activity: bool | None = None
    auto_interval_sec: int | None = Field(default=None, ge=1, le=60)

    @field_validator("priority_weights")
    @classmethod
    def weights_ok(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return v
        required = {"urgency", "overdue", "demand", "fine", "risk", "history"}
        if set(v) != required:
            raise ValueError(f"Weights must contain exactly: {', '.join(sorted(required))}")
        if any(w < 0 or w > 100 for w in v.values()):
            raise ValueError("Each weight must be between 0 and 100")
        if sum(v.values()) <= 0:
            raise ValueError("At least one weight must be positive")
        return v

    @field_validator("cooldown_days")
    @classmethod
    def cooldowns_ok(cls, v: dict[str, int] | None) -> dict[str, int] | None:
        if v is not None and any(d < 0 or d > 30 for d in v.values()):
            raise ValueError("Cooldowns must be between 0 and 30 days")
        return v
