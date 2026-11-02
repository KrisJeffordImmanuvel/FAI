from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import db as dbm
from .. import serializers as S
from ..db import get_db
from ..deps import current_user, staff
from ..models import AgentCycle, AgentEvent, Approval, Notification, User
from ..schemas import AdvanceIn, RunIn
from ..services import agent, demo, fuzzy, simulation
from ..services.audit import audit
from ..services.priority import FACTOR_LABELS, KIND_FLOOR, KIND_URGENCY

router = APIRouter(prefix="/api", tags=["agent"])


@router.get("/agent/status")
def status(db: Session = Depends(get_db), _user: User = Depends(current_user)) -> dict:
    out = simulation.status(db)
    out["cycles"] = db.scalar(select(func.count(AgentCycle.id))) or 0
    out["pending_approvals"] = db.scalar(select(func.count(Approval.id)).where(Approval.status == "pending")) or 0
    out["queued_notifications"] = db.scalar(select(func.count(Notification.id)).where(Notification.status == "queued")) or 0
    return out


@router.post("/agent/run")
def run(body: RunIn | None = None, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    cycle = agent.run_cycle(db, (body or RunIn()).mode)
    audit(db, "agent.run", "agent_cycle", cycle.id, user, {"mode": cycle.mode})
    db.commit()
    return S.cycle(cycle)


@router.post("/agent/advance")
def advance(body: AdvanceIn, db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    cycles = simulation.advance(db, body.days, body.run_agent)
    audit(db, "clock.advance", "clock", None, user, {"days": body.days, "run_agent": body.run_agent})
    db.commit()
    return {"status": simulation.status(db), "cycles": [S.cycle(c) for c in cycles]}


@router.post("/agent/reset")
def reset(db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    """Restore the original seeded state (re-runs the deterministic seeder)."""
    from ..seed import reset_database

    db.close()
    dbm.engine.dispose()
    reset_database(verbose=False)
    with dbm.SessionLocal() as fresh:
        return {"status": simulation.status(fresh)}


@router.get("/agent/cycles")
def cycles(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db), _user: User = Depends(staff)) -> list[dict]:
    return [S.cycle(c) for c in db.scalars(select(AgentCycle).order_by(AgentCycle.id.desc()).limit(limit))]


@router.get("/agent/cycles/{cycle_id}")
def cycle_detail(cycle_id: int, db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    c = db.get(AgentCycle, cycle_id)
    if c is None:
        raise HTTPException(404, "Cycle not found")
    out = S.cycle(c, detail=True)
    out["events"] = [S.event(e) for e in db.scalars(select(AgentEvent).where(AgentEvent.cycle_id == c.id).order_by(AgentEvent.id))]
    out["notifications"] = [S.notification(n) for n in db.scalars(select(Notification).where(Notification.cycle_id == c.id).order_by(Notification.id))]
    return out


@router.get("/agent/events")
def events(
    after_id: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=300),
    phase: str = Query("", pattern="^(|perceive|think|act|human|system|demo)$"),
    db: Session = Depends(get_db),
    _user: User = Depends(staff),
) -> list[dict]:
    q = select(AgentEvent)
    if phase:
        q = q.where(AgentEvent.phase == phase)
    if after_id:
        rows = db.scalars(q.where(AgentEvent.id > after_id).order_by(AgentEvent.id).limit(limit)).all()
    else:
        rows = list(reversed(db.scalars(q.order_by(AgentEvent.id.desc()).limit(limit)).all()))
    return [S.event(e) for e in rows]


@router.get("/demo")
def get_demo(db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    return _demo_payload(db, demo.get_demo(db))


def _demo_payload(db: Session, data: dict) -> dict:
    ids = [i for entry in (data.get("state") or {}).get("log", []) for i in entry["event_ids"]]
    evs = {e.id: S.event(e) for e in db.scalars(select(AgentEvent).where(AgentEvent.id.in_(ids)))} if ids else {}
    for entry in (data.get("state") or {}).get("log", []):
        entry["events"] = [evs[i] for i in entry["event_ids"] if i in evs]
    data["status"] = simulation.status(db)
    return data


@router.post("/demo/start")
def demo_start(db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    data = demo.start(db, user)
    db.commit()
    return _demo_payload(db, data)


@router.post("/demo/next")
def demo_next(db: Session = Depends(get_db), user: User = Depends(staff)) -> dict:
    data = demo.next_step(db, user)
    db.commit()
    return _demo_payload(db, data)


@router.get("/explain/loan/{loan_id}")
def explain_loan(loan_id: int, db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    return agent.explain_loan(db, loan_id)


@router.get("/explain/fuzzy")
def fuzzy_model(_user: User = Depends(current_user)) -> dict:
    return {
        "curves": fuzzy.membership_curves(),
        "rules": [{"id": rid, "if": text, "then": level} for rid, text, level, _ in fuzzy.RULES],
        "centroids": fuzzy.LEVEL_CENTROIDS,
        "kind_urgency": KIND_URGENCY,
        "kind_floor": KIND_FLOOR,
        "factor_labels": FACTOR_LABELS,
    }


@router.get("/explain/fuzzy/evaluate")
def fuzzy_eval(
    lateness: float = Query(0, ge=-30, le=120),
    demand: float = Query(0, ge=0, le=20),
    fine: float = Query(0, ge=0, le=5000),
    risk: float = Query(0, ge=0, le=1),
    _user: User = Depends(current_user),
) -> dict:
    return fuzzy.classify(lateness, demand, fine, risk).to_dict()
