"""Late-return risk prediction (decision support only).

* The training data is a **synthetic**, reproducible dataset (fixed seed).
  Optionally the library's own completed loans are appended — their feature
  snapshots were frozen at checkout time.
* Only features known **at checkout** are used (no leakage): the return date,
  renewals, fines and notifications that happen *after* checkout are excluded.
* No sensitive personal attributes (gender, age, religion, caste, address,
  disability, nationality, name) are collected or used.
* Logistic Regression and a Decision Tree are trained and compared; the best
  F1 model is selected automatically (an admin can override the choice).
* Predictions never set fines or penalties; they only tune reminder priority.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..models import Loan, MLModel

CATEGORIES = [
    "Computer Science",
    "Artificial Intelligence",
    "Mathematics",
    "Physics",
    "Electronics",
    "Mechanical Engineering",
    "Literature",
    "History",
    "Economics",
    "Management",
    "Biology",
    "Philosophy",
]
MEMBER_TYPES = ["student", "faculty", "staff"]
LOAN_DAYS = {"student": 14, "faculty": 30, "staff": 21}

NUMERIC = ["prior_loans", "prior_late_rate", "unpaid_fines", "active_loans", "title_demand", "loan_days", "exam_period", "weekend_checkout"]
CATEGORICAL = ["member_type", "category"]
FEATURES = NUMERIC + CATEGORICAL

FEATURE_DOCS = {
    "prior_loans": "Number of loans the member completed before this checkout",
    "prior_late_rate": "Share of those earlier loans returned late",
    "unpaid_fines": "Unpaid fines (₹) at the moment of checkout",
    "active_loans": "Other books already on loan at checkout",
    "title_demand": "Members waiting for this title at checkout",
    "loan_days": "Loan period granted by policy",
    "exam_period": "Checkout during an exam month (1 = yes)",
    "weekend_checkout": "Checked out on Saturday/Sunday (1 = yes)",
    "member_type": "Membership category (student/faculty/staff) — an academic role, not a personal attribute",
    "category": "Subject category of the book",
}

EXCLUDED_LEAKAGE = [
    "returned_on / actual days late (this is the label itself)",
    "number of renewals (happens after checkout)",
    "fine amount on this loan (computed after the due date)",
    "notifications received for this loan (sent after checkout)",
]
EXCLUDED_SENSITIVE = ["name", "gender", "age / date of birth", "religion / caste", "home address", "nationality", "disability status", "phone / email"]

_EXAM_MONTHS = {4, 5, 11, 12}
_CATEGORY_EFFECT = {
    "Computer Science": 0.10,
    "Artificial Intelligence": 0.15,
    "Mathematics": 0.25,
    "Physics": 0.20,
    "Electronics": 0.05,
    "Mechanical Engineering": 0.05,
    "Literature": -0.20,
    "History": -0.10,
    "Economics": 0.0,
    "Management": -0.05,
    "Biology": 0.10,
    "Philosophy": -0.15,
}
_TYPE_EFFECT = {"student": 0.35, "faculty": -0.25, "staff": -0.05}


def is_exam_period(d: date) -> int:
    return int(d.month in _EXAM_MONTHS)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def latent_late_probability(features: dict[str, Any], habit: float) -> float:
    """The *hidden* data-generating process (also used by the seeder for consistency)."""
    logit = (
        -2.35
        + 3.2 * habit
        + 0.0035 * features["unpaid_fines"]
        + 0.22 * features["active_loans"]
        + 0.55 * features["exam_period"]
        + 0.25 * features["weekend_checkout"]
        + 0.12 * features["title_demand"]
        - 0.02 * (features["loan_days"] - 14)
        + _TYPE_EFFECT[features["member_type"]]
        + _CATEGORY_EFFECT[features["category"]]
    )
    return float(1 / (1 + math.exp(-logit)))


def generate_dataset(n: int = 4000, seed: int = 42) -> list[dict[str, Any]]:
    """Reproducible SYNTHETIC checkout records with a ``late`` label."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    types = rng.choice(MEMBER_TYPES, size=n, p=[0.72, 0.18, 0.10])
    for i in range(n):
        mtype = str(types[i])
        habit = float(rng.beta(2.0, 5.5))  # hidden tardiness habit of the member
        prior = int(rng.poisson({"student": 10, "faculty": 18, "staff": 7}[mtype]))
        late_prior = int(rng.binomial(prior, min(habit * 1.1, 0.95))) if prior else 0
        unpaid = float(round(rng.gamma(2.0, 35 * (1 + 3 * habit)))) if rng.random() < 0.15 + 0.6 * habit else 0.0
        feats = {
            "prior_loans": prior,
            "prior_late_rate": round(late_prior / prior, 3) if prior else 0.0,
            "unpaid_fines": unpaid,
            "active_loans": int(min(rng.poisson(1.0 + habit), {"student": 4, "faculty": 9, "staff": 5}[mtype])),
            "title_demand": int(min(rng.poisson(0.6), 5)),
            "loan_days": LOAN_DAYS[mtype],
            "exam_period": int(rng.random() < 0.3),
            "weekend_checkout": int(rng.random() < 2 / 7),
            "member_type": mtype,
            "category": str(rng.choice(CATEGORIES)),
        }
        p = latent_late_probability(feats, habit)
        feats["late"] = int(rng.random() < p)
        feats["synthetic"] = True
        rows.append(feats)
    return rows


def _matrix(rows: list[dict[str, Any]]) -> tuple[dict[str, np.ndarray], np.ndarray]:
    X = {f: np.array([r[f] for r in rows], dtype=object if f in CATEGORICAL else float) for f in FEATURES}
    y = np.array([int(r["late"]) for r in rows])
    return X, y


def _to_frame(X: dict[str, np.ndarray], idx: np.ndarray | None = None):  # noqa: ANN202
    """Build a column-oriented structure sklearn's ColumnTransformer accepts (no pandas needed)."""
    cols = [X[f] if idx is None else X[f][idx] for f in FEATURES]
    arr = np.empty((len(cols[0]), len(FEATURES)), dtype=object)
    for j, c in enumerate(cols):
        arr[:, j] = c
    return arr


def _preprocessor(scale: bool) -> ColumnTransformer:
    num_idx = [FEATURES.index(f) for f in NUMERIC]
    cat_idx = [FEATURES.index(f) for f in CATEGORICAL]
    return ColumnTransformer(
        [
            ("num", StandardScaler() if scale else "passthrough", num_idx),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_idx),
        ]
    )


def _feature_names(pre: ColumnTransformer) -> list[str]:
    names = list(NUMERIC)
    enc: OneHotEncoder = pre.named_transformers_["cat"]
    for feat, cats in zip(CATEGORICAL, enc.categories_, strict=True):
        names.extend(f"{feat}={c}" for c in cats)
    return names


def build_models(seed: int) -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline(
            [("pre", _preprocessor(scale=True)), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))]
        ),
        "decision_tree": Pipeline(
            [
                ("pre", _preprocessor(scale=False)),
                ("clf", DecisionTreeClassifier(max_depth=5, min_samples_leaf=25, class_weight="balanced", random_state=seed)),
            ]
        ),
    }


def _importance(algo: str, pipe: Pipeline) -> list[dict[str, Any]]:
    names = _feature_names(pipe.named_steps["pre"])
    clf = pipe.named_steps["clf"]
    if algo == "logistic_regression":
        coefs = clf.coef_[0]
        total = float(np.abs(coefs).sum()) or 1.0
        items = [
            {"feature": n, "importance": round(abs(float(c)) / total, 4), "direction": "raises risk" if c > 0 else "lowers risk", "coefficient": round(float(c), 4)}
            for n, c in zip(names, coefs, strict=True)
        ]
    else:
        items = [
            {"feature": n, "importance": round(float(v), 4), "direction": "split feature"}
            for n, v in zip(names, clf.feature_importances_, strict=True)
        ]
    return sorted(items, key=lambda d: -d["importance"])


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> dict[str, Any]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def _history_rows(db: Session) -> list[dict[str, Any]]:
    rows = []
    loans = db.scalars(select(Loan).where(Loan.status == "returned", Loan.returned_on.is_not(None))).all()
    for loan in loans:
        feats = (loan.risk_detail or {}).get("features")
        if not feats or any(f not in feats for f in FEATURES):
            continue
        row = {f: feats[f] for f in FEATURES}
        row["late"] = int(loan.returned_on > loan.due_on)  # type: ignore[operator]
        row["synthetic"] = False
        rows.append(row)
    return rows


def train_and_compare(db: Session, n_samples: int = 4000, seed: int = 42, include_history: bool = True) -> list[MLModel]:
    synthetic = generate_dataset(n_samples, seed)
    history = _history_rows(db) if include_history else []
    rows = synthetic + history
    X, y = _matrix(rows)
    idx = np.arange(len(y))
    train_idx, test_idx = train_test_split(idx, test_size=0.25, random_state=seed, stratify=y)
    Xtr, Xte = _to_frame(X, train_idx), _to_frame(X, test_idx)
    ytr, yte = y[train_idx], y[test_idx]
    test_types = X["member_type"][test_idx]

    version = (db.scalar(select(func.max(MLModel.version))) or 0) + 1
    created: list[MLModel] = []
    for algo, pipe in build_models(seed).items():
        pipe.fit(Xtr, ytr)
        prob = pipe.predict_proba(Xte)[:, 1]
        pred = (prob >= 0.5).astype(int)
        metrics = _metrics(yte, pred, prob)
        fairness = {}
        for t in MEMBER_TYPES:
            mask = test_types == t
            if mask.sum() == 0:
                continue
            fairness[t] = {
                "n": int(mask.sum()),
                "actual_late_rate": round(float(yte[mask].mean()), 3),
                "predicted_high_rate": round(float(pred[mask].mean()), 3),
                "recall": round(float(recall_score(yte[mask], pred[mask], zero_division=0)), 3),
            }
        metrics["by_member_type"] = fairness
        path = Path(config.MODELS_DIR) / f"{algo}_v{version}.joblib"
        joblib.dump({"pipeline": pipe, "algo": algo, "features": FEATURES}, path)
        params = {k: v for k, v in pipe.named_steps["clf"].get_params().items() if isinstance(v, (int, float, str, bool, type(None)))}
        model = MLModel(
            algo=algo,
            version=version,
            path=str(path),
            params=params,
            metrics=metrics,
            feature_importance=_importance(algo, pipe),
            dataset_info={
                "synthetic_rows": len(synthetic),
                "history_rows": len(history),
                "train_rows": int(len(train_idx)),
                "test_rows": int(len(test_idx)),
                "positive_rate": round(float(y.mean()), 3),
                "seed": seed,
                "label": "SYNTHETIC dataset (generated, reproducible) + library loan history",
            },
        )
        db.add(model)
        created.append(model)
    db.flush()
    best = max(created, key=lambda m: (m.metrics["f1"], m.metrics["roc_auc"]))
    select_model(db, best.id)
    return created


def select_model(db: Session, model_id: int) -> MLModel:
    target = db.get(MLModel, model_id)
    if target is None:
        raise ValueError("Model not found")
    for m in db.scalars(select(MLModel).where(MLModel.is_selected.is_(True))):
        m.is_selected = False
    target.is_selected = True
    _CACHE.clear()
    return target


_CACHE: dict[tuple[int, str], dict[str, Any]] = {}


def _load_selected(db: Session) -> tuple[MLModel, dict[str, Any]] | None:
    model = db.scalar(select(MLModel).where(MLModel.is_selected.is_(True)))
    if model is None:
        return None
    key = (model.id, model.path)
    if key not in _CACHE:
        if not Path(model.path).exists():
            return None
        _CACHE.clear()
        _CACHE[key] = joblib.load(model.path)
    return model, _CACHE[key]


def risk_label(p: float) -> str:
    return "high" if p >= 0.6 else ("medium" if p >= 0.35 else "low")


def _explain_lr(pipe: Pipeline, row: np.ndarray, features: dict[str, Any]) -> list[dict[str, Any]]:
    pre = pipe.named_steps["pre"]
    clf = pipe.named_steps["clf"]
    xt = pre.transform(row)[0]
    names = _feature_names(pre)
    out = []
    for name, coef, x in zip(names, clf.coef_[0], xt, strict=True):
        contribution = float(coef * x)
        if "=" in name and x == 0:
            continue  # inactive category
        base = name.split("=")[0]
        out.append(
            {
                "feature": name,
                "value": features.get(base),
                "contribution": round(contribution, 4),
                "effect": "raises risk" if contribution > 0 else "lowers risk",
                "text": f"{name if '=' in name else base} = {features.get(base)}",
            }
        )
    out.sort(key=lambda d: -abs(d["contribution"]))
    return out[:5]


def _explain_tree(pipe: Pipeline, row: np.ndarray, features: dict[str, Any]) -> list[dict[str, Any]]:
    pre = pipe.named_steps["pre"]
    clf: DecisionTreeClassifier = pipe.named_steps["clf"]
    xt = pre.transform(row)
    names = _feature_names(pre)
    tree = clf.tree_
    path = clf.decision_path(xt).indices
    steps = []
    for node in path:
        if tree.children_left[node] == tree.children_right[node]:
            continue  # leaf
        fi = tree.feature[node]
        thr = float(tree.threshold[node])
        val = float(xt[0, fi])
        name = names[fi]
        if "=" in name:
            text = f"{name.replace('=', ' is ')}" if val > thr else f"{name.replace('=', ' is not ')}"
        else:
            text = f"{name} = {features.get(name)} {'>' if val > thr else '≤'} {thr:.3g}"
        child = tree.children_right[node] if val > thr else tree.children_left[node]
        values = tree.value[child][0]
        p_late = float(values[1] / values.sum()) if values.sum() else 0.0
        steps.append({"feature": name, "text": text, "risk_after_step": round(p_late, 3)})
    return steps


def predict(db: Session, features: dict[str, Any]) -> dict[str, Any] | None:
    """Probability of a late return with the main factors behind it."""
    loaded = _load_selected(db)
    if loaded is None:
        return None
    model, bundle = loaded
    pipe: Pipeline = bundle["pipeline"]
    clean = {f: features[f] for f in FEATURES}
    row = np.empty((1, len(FEATURES)), dtype=object)
    for j, f in enumerate(FEATURES):
        row[0, j] = clean[f]
    p = float(pipe.predict_proba(row)[0, 1])
    factors = _explain_lr(pipe, row, clean) if model.algo == "logistic_regression" else _explain_tree(pipe, row, clean)
    return {
        "probability": round(p, 4),
        "label": risk_label(p),
        "model": {"id": model.id, "algo": model.algo, "version": model.version},
        "factors": factors,
        "features": clean,
        "note": "Decision support only — never used to set fines or penalties.",
    }
