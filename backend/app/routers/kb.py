from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import admin_only, current_user
from ..models import Rule, User
from ..schemas import RuleIn, RuleTestIn
from ..services import knowledge_base as kb
from ..services.audit import audit
from ..services.inference import RuleSpec, forward_chain

router = APIRouter(prefix="/api/kb", tags=["knowledge base"])


def _all(db: Session) -> list[dict]:
    return [S.rule(r) for r in db.scalars(select(Rule).order_by(Rule.entity, Rule.salience.desc(), Rule.code))]


@router.get("/rules")
def rules(db: Session = Depends(get_db), _user: User = Depends(current_user)) -> dict:
    items = _all(db)
    return {"items": items, "tainted": kb.tainted_facts(items)}


@router.get("/schema")
def schema(_user: User = Depends(current_user)) -> dict:
    return kb.schema()


@router.post("/validate")
def validate(body: RuleIn, db: Session = Depends(get_db), _user: User = Depends(current_user)) -> dict:
    errors = kb.validate_rule(body.model_dump(), _all(db))
    return {"valid": not errors, "errors": errors}


def _check(db: Session, data: dict, exclude_id: int | None = None) -> None:
    existing = [r for r in _all(db) if r["id"] != exclude_id]
    errors = kb.validate_rule(data, existing)
    if any(r["code"] == data["code"] for r in existing):
        errors.insert(0, f"Rule code {data['code']} already exists.")
    if errors:
        raise HTTPException(422, {"message": "Rule is not valid", "errors": errors})


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    data = body.model_dump()
    _check(db, data)
    rule = Rule(**data)
    db.add(rule)
    db.flush()
    audit(db, "kb.create", "rule", rule.id, user, {"code": rule.code})
    db.commit()
    return S.rule(rule)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    data = body.model_dump()
    _check(db, data, exclude_id=rule_id)
    for k, v in data.items():
        setattr(rule, k, v)
    audit(db, "kb.update", "rule", rule.id, user, {"code": rule.code})
    db.commit()
    return S.rule(rule)


@router.delete("/rules/{rule_id}", status_code=204, response_class=Response, response_model=None)
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> None:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    audit(db, "kb.delete", "rule", rule.id, user, {"code": rule.code})
    db.delete(rule)
    db.commit()
    return Response(status_code=204)


@router.post("/reset")
def reset_rules(db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    for r in db.scalars(select(Rule)):
        db.delete(r)
    db.flush()
    for r in kb.DEFAULT_RULES:
        db.add(Rule(**r))
    audit(db, "kb.reset", "rule", None, user, {})
    db.commit()
    return {"items": _all(db)}


@router.post("/test")
def test_rules(body: RuleTestIn, db: Session = Depends(get_db), _user: User = Depends(current_user)) -> dict:
    """Run forward chaining over a hand-written fact frame (sandbox — nothing is stored)."""
    allowed = set(kb.FIELDS[body.entity])
    facts = {k: v for k, v in body.facts.items() if k in allowed}
    memory = {(body.entity, 0): dict(facts)}
    trace = forward_chain(memory, [RuleSpec.from_obj(r) for r in db.scalars(select(Rule))])
    frame = memory[(body.entity, 0)]
    return {
        "firings": [f.to_dict() for f in trace],
        "asserted": [c for c in kb.CONCLUSIONS if frame.get(c)],
        "actions": [c for c in kb.CONCLUSIONS if frame.get(c) and kb.CONCLUSIONS[c]["kind"] == "action"],
    }
