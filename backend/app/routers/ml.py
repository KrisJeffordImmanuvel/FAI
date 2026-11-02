from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import admin_only, staff
from ..models import Loan, MLModel, User
from ..schemas import PredictIn, RetrainIn
from ..services import ml
from ..services.audit import audit

router = APIRouter(prefix="/api/ml", tags=["machine learning"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    models = db.scalars(select(MLModel).order_by(MLModel.version.desc(), MLModel.algo)).all()
    latest_version = models[0].version if models else None
    sample = ml.generate_dataset(12, seed=7)
    active = db.scalars(select(Loan).where(Loan.status == "active", Loan.risk_score.is_not(None)).order_by(Loan.risk_score.desc()).limit(8)).all()
    return {
        "latest": [S.ml_model(m) for m in models if m.version == latest_version],
        "history": [S.ml_model(m) for m in models],
        "selected": next((S.ml_model(m) for m in models if m.is_selected), None),
        "features": [{"name": f, "description": ml.FEATURE_DOCS[f], "type": "categorical" if f in ml.CATEGORICAL else "numeric"} for f in ml.FEATURES],
        "excluded_leakage": ml.EXCLUDED_LEAKAGE,
        "excluded_sensitive": ml.EXCLUDED_SENSITIVE,
        "categories": ml.CATEGORIES,
        "sample_rows": sample,
        "top_risk_loans": [
            {"loan_id": lo.id, "title": lo.copy.book.title, "member_name": lo.member.name, "risk_score": lo.risk_score, "risk_label": lo.risk_label,
             "factors": (lo.risk_detail or {}).get("factors", []), "algo": ((lo.risk_detail or {}).get("model") or {}).get("algo")}
            for lo in active
        ],
    }


@router.post("/retrain")
def retrain(body: RetrainIn, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    created = ml.train_and_compare(db, body.n_samples, body.seed, body.include_history)
    audit(db, "ml.retrain", "ml_model", created[0].id, user, body.model_dump())
    db.commit()
    return {"models": [S.ml_model(m) for m in created]}


@router.post("/models/{model_id}/select")
def select_model(model_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    try:
        m = ml.select_model(db, model_id)
    except ValueError:
        raise HTTPException(404, "Model not found") from None
    audit(db, "ml.select", "ml_model", m.id, user, {"algo": m.algo, "version": m.version})
    db.commit()
    return S.ml_model(m)


@router.post("/predict")
def predict(body: PredictIn, db: Session = Depends(get_db), _user: User = Depends(staff)) -> dict:
    if body.category not in ml.CATEGORIES:
        raise HTTPException(422, "Unknown category")
    result = ml.predict(db, body.model_dump())
    if result is None:
        raise HTTPException(409, "No trained model is selected yet — retrain first")
    return result
