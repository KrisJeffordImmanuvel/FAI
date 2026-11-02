"""SQLAlchemy ORM models for the library agent."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # admin | librarian | member
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    member: Mapped[Member | None] = relationship(back_populates="user")


class Policy(Base):
    """Circulation and fine rules per member type (student, faculty, staff)."""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_type: Mapped[str] = mapped_column(String(20), unique=True)
    label: Mapped[str] = mapped_column(String(60))
    max_loans: Mapped[int] = mapped_column(Integer)
    loan_days: Mapped[int] = mapped_column(Integer)
    max_renewals: Mapped[int] = mapped_column(Integer)
    max_reservations: Mapped[int] = mapped_column(Integer)
    grace_days: Mapped[int] = mapped_column(Integer)
    fine_slabs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    max_fine: Mapped[float] = mapped_column(Float)
    exclude_sundays: Mapped[bool] = mapped_column(Boolean, default=True)
    lost_after_days: Mapped[int] = mapped_column(Integer)
    lost_processing_fee: Mapped[float] = mapped_column(Float)
    hold_days: Mapped[int] = mapped_column(Integer)


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), unique=True)
    phone: Mapped[str] = mapped_column(String(20))
    member_type: Mapped[str] = mapped_column(String(20))
    department: Mapped[str] = mapped_column(String(60))
    joined_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|restricted|suspended
    restriction_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notify_pref: Mapped[str] = mapped_column(String(10), default="email")  # in_app|email|sms

    user: Mapped[User | None] = relationship(back_populates="member")
    loans: Mapped[list[Loan]] = relationship(back_populates="member")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    author: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    publisher: Mapped[str] = mapped_column(String(120))
    year: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)  # replacement cost used for lost books
    description: Mapped[str] = mapped_column(Text, default="")

    copies: Mapped[list[Copy]] = relationship(back_populates="book", order_by="Copy.id")


class Copy(Base):
    """A physical, barcoded copy of a title."""

    __tablename__ = "copies"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    barcode: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|on_loan|on_hold|lost|maintenance
    shelf: Mapped[str] = mapped_column(String(20))
    acquired_on: Mapped[date] = mapped_column(Date)

    book: Mapped[Book] = relationship(back_populates="copies")


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        # A copy can only be on one active loan at a time (race-condition guard).
        Index("uq_active_loan_per_copy", "copy_id", unique=True, sqlite_where=text("status = 'active'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(ForeignKey("copies.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    issued_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date, index=True)
    returned_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    renewals: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|returned|lost
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_label: Mapped[str | None] = mapped_column(String(10), nullable=True)
    risk_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    copy: Mapped[Copy] = relationship()
    member: Mapped[Member] = relationship(back_populates="loans")
    fine: Mapped[Fine | None] = relationship(back_populates="loan", uselist=False)


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index(
            "uq_open_reservation",
            "book_id",
            "member_id",
            unique=True,
            sqlite_where=text("status IN ('waiting', 'ready')"),
        ),
        # A copy can be held for at most one reservation.
        Index("uq_hold_per_copy", "copy_id", unique=True, sqlite_where=text("status = 'ready'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    created_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)  # waiting|ready|fulfilled|cancelled|expired
    copy_id: Mapped[int | None] = mapped_column(ForeignKey("copies.id"), nullable=True)
    ready_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    book: Mapped[Book] = relationship()
    member: Mapped[Member] = relationship()
    copy: Mapped[Copy | None] = relationship()


class Fine(Base):
    __tablename__ = "fines"

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), unique=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="overdue")  # overdue|lost
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0)
    amount_waived: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="accruing", index=True)  # accruing|open|partially_paid|paid|waived
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_on: Mapped[date] = mapped_column(Date)
    last_computed_on: Mapped[date] = mapped_column(Date)

    loan: Mapped[Loan] = relationship(back_populates="fine")
    member: Mapped[Member] = relationship()
    payments: Mapped[list[Payment]] = relationship(order_by="Payment.id")
    waivers: Mapped[list[Waiver]] = relationship(order_by="Waiver.id")

    @property
    def balance(self) -> float:
        return round(max(self.amount - self.amount_paid - self.amount_waived, 0.0), 2)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    fine_id: Mapped[int] = mapped_column(ForeignKey("fines.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20))
    paid_on: Mapped[date] = mapped_column(Date)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Waiver(Base):
    __tablename__ = "waivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    fine_id: Mapped[int] = mapped_column(ForeignKey("fines.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(500))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    waived_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(120))


class Approval(Base):
    """Human-in-the-loop queue for high-impact actions."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # waiver|restrict_member|mark_lost
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected|withdrawn
    source: Mapped[str] = mapped_column(String(20))  # agent|member|librarian
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id"), nullable=True)
    fine_id: Mapped[int | None] = mapped_column(ForeignKey("fines.id"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(String(500))
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    requested_by_label: Mapped[str] = mapped_column(String(120))
    requested_by_user: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    member: Mapped[Member | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id"), nullable=True)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"), nullable=True)
    fine_id: Mapped[int | None] = mapped_column(ForeignKey("fines.id"), nullable=True)
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(10), index=True)  # Critical|High|Medium|Low
    channel: Mapped[str] = mapped_column(String(10))  # in_app|email|sms
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(15), index=True)  # queued|sent|suppressed|read
    suppression_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(80), index=True)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(15), default="pending")  # pending|resolved|ignored|n/a
    created_on: Mapped[date] = mapped_column(Date, index=True)
    sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("agent_cycles.id"), nullable=True)

    member: Mapped[Member] = relationship()


class Rule(Base):
    """A production rule in the editable knowledge base."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    entity: Mapped[str] = mapped_column(String(20))  # loan|member|reservation|fine
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    conclusion: Mapped[str] = mapped_column(String(40))
    salience: Mapped[int] = mapped_column(Integer, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class AgentCycle(Base):
    __tablename__ = "agent_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    sim_date: Mapped[date] = mapped_column(Date, index=True)
    mode: Mapped[str] = mapped_column(String(20))  # manual|auto|advance|demo
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    percepts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    firings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")


class AgentEvent(Base):
    """Timeline entry shown in the live decision feed."""

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("agent_cycles.id"), nullable=True, index=True)
    sim_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    phase: Mapped[str] = mapped_column(String(15))  # perceive|think|act|human|system|demo
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info|success|warning|critical
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id"), nullable=True)


class MLModel(Base):
    __tablename__ = "ml_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    algo: Mapped[str] = mapped_column(String(40))  # logistic_regression|decision_tree
    version: Mapped[int] = mapped_column(Integer)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    path: Mapped[str] = mapped_column(String(255))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    feature_importance: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    dataset_info: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sim_date: Mapped[date] = mapped_column(Date)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
