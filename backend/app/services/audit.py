"""Audit log and agent-timeline helpers."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import AgentEvent, AuditLog, User
from .settings import today


def audit(
    db: Session,
    action: str,
    entity: str,
    entity_id: int | None,
    actor: User | None = None,
    details: dict[str, Any] | None = None,
    actor_label: str | None = None,
) -> None:
    db.add(
        AuditLog(
            sim_date=today(db),
            actor_user_id=actor.id if actor else None,
            actor_label=actor_label or (f"{actor.name} ({actor.role})" if actor else "Agent"),
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details or {},
        )
    )


def event(
    db: Session,
    phase: str,
    kind: str,
    title: str,
    detail: str = "",
    severity: str = "info",
    data: dict[str, Any] | None = None,
    cycle_id: int | None = None,
    member_id: int | None = None,
    loan_id: int | None = None,
) -> AgentEvent:
    ev = AgentEvent(
        cycle_id=cycle_id,
        sim_date=today(db),
        phase=phase,
        kind=kind,
        severity=severity,
        title=title,
        detail=detail,
        data=data or {},
        member_id=member_id,
        loan_id=loan_id,
    )
    db.add(ev)
    return ev
