"""Fuzzy-logic priority classifier (Mamdani-style with singleton outputs).

Crisp inputs → fuzzification (membership degrees) → rule evaluation
(AND = min, OR = max) → aggregation per output level (max) → the level with
the strongest support wins, and a crisp 0-100 value is obtained with the
weighted-average (centroid of singletons) defuzzifier.

Inputs
------
lateness  signed days relative to the due date (negative = days left, positive = days overdue)
demand    number of members waiting for the title
fine      fine amount in rupees
risk      predicted late-return probability (0-1)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

LEVELS = ("Low", "Medium", "High", "Critical")
LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}
LEVEL_CENTROIDS = {"Low": 15.0, "Medium": 40.0, "High": 65.0, "Critical": 90.0}
INF = math.inf


def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoidal membership; a/b may be -inf and c/d may be +inf for shoulders."""
    if x < a or x > d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if x < b:
        return 1.0 if b == a else (x - a) / (b - a)
    return 1.0 if d == c else (d - x) / (d - c)


def triangle(x: float, a: float, b: float, c: float) -> float:
    return trapezoid(x, a, b, b, c)


# (name, shape, params) — exposed so the UI can draw the membership functions.
MEMBERSHIP_FUNCTIONS: dict[str, dict[str, Any]] = {
    "lateness": {
        "label": "Lateness (days; negative = days left)",
        "range": [-7, 25],
        "sets": {
            "early": ("trap", (-INF, -INF, -4, -2)),
            "due_soon": ("tri", (-3, -1, 1)),
            "slightly_overdue": ("tri", (0, 3, 7)),
            "moderately_overdue": ("tri", (5, 10, 16)),
            "severely_overdue": ("trap", (13, 20, INF, INF)),
        },
    },
    "demand": {
        "label": "Reservation demand (members waiting)",
        "range": [0, 6],
        "sets": {
            "low": ("trap", (-INF, -INF, 0, 1)),
            "medium": ("tri", (0, 1.5, 3)),
            "high": ("trap", (2, 4, INF, INF)),
        },
    },
    "fine": {
        "label": "Fine amount (₹)",
        "range": [0, 600],
        "sets": {
            "small": ("trap", (-INF, -INF, 30, 80)),
            "moderate": ("tri", (50, 175, 300)),
            "large": ("trap", (220, 400, INF, INF)),
        },
    },
    "risk": {
        "label": "Predicted late-return risk",
        "range": [0, 1],
        "sets": {
            "low": ("trap", (-INF, -INF, 0.25, 0.45)),
            "medium": ("tri", (0.3, 0.5, 0.7)),
            "high": ("trap", (0.55, 0.75, INF, INF)),
        },
    },
}

# Each rule: (id, antecedent description, output level, evaluator(memberships) -> strength)
_Rule = tuple[str, str, str, Any]


def _rules() -> list[_Rule]:
    def m(var: str, s: str):  # noqa: ANN202
        return lambda mu: mu[var][s]

    def AND(*fs):  # noqa: ANN202, N802
        return lambda mu: min(f(mu) for f in fs)

    def OR(*fs):  # noqa: ANN202, N802
        return lambda mu: max(f(mu) for f in fs)

    L, D, F, R = "lateness", "demand", "fine", "risk"
    return [
        ("F1", "lateness is severely_overdue", "Critical", m(L, "severely_overdue")),
        ("F2", "lateness is moderately_overdue AND demand is high", "Critical", AND(m(L, "moderately_overdue"), m(D, "high"))),
        ("F3", "lateness is moderately_overdue AND demand is (low OR medium)", "High",
         AND(m(L, "moderately_overdue"), OR(m(D, "low"), m(D, "medium")))),
        ("F4", "lateness is slightly_overdue AND demand is (medium OR high)", "High",
         AND(m(L, "slightly_overdue"), OR(m(D, "medium"), m(D, "high")))),
        ("F5", "lateness is slightly_overdue AND demand is low", "Medium", AND(m(L, "slightly_overdue"), m(D, "low"))),
        ("F6", "fine is large", "High", m(F, "large")),
        ("F7", "fine is moderate", "Medium", m(F, "moderate")),
        ("F8", "lateness is due_soon AND (risk is high OR demand is high)", "Medium",
         AND(m(L, "due_soon"), OR(m(R, "high"), m(D, "high")))),
        ("F9", "lateness is due_soon AND risk is (low OR medium)", "Low", AND(m(L, "due_soon"), OR(m(R, "low"), m(R, "medium")))),
        ("F10", "lateness is early", "Low", m(L, "early")),
    ]


RULES = _rules()


def fuzzify(variable: str, x: float) -> dict[str, float]:
    out = {}
    for name, (shape, params) in MEMBERSHIP_FUNCTIONS[variable]["sets"].items():
        value = trapezoid(x, *params) if shape == "trap" else triangle(x, *params)
        out[name] = round(value, 4)
    return out


@dataclass
class FuzzyResult:
    level: str
    crisp: float
    inputs: dict[str, Any]
    memberships: dict[str, dict[str, float]]
    activations: list[dict[str, Any]]
    output_strengths: dict[str, float]
    floor_applied: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "crisp": self.crisp,
            "inputs": self.inputs,
            "memberships": self.memberships,
            "activations": self.activations,
            "output_strengths": self.output_strengths,
            "floor_applied": self.floor_applied,
        }


def classify(lateness: float | None, demand: float, fine: float, risk: float, floor: str | None = None) -> FuzzyResult:
    """``lateness=None`` means "not applicable": every lateness set gets membership 0."""
    inputs: dict[str, Any] = {"lateness": None if lateness is None else float(lateness), "demand": float(demand), "fine": float(fine), "risk": float(risk)}
    mu = {var: (dict.fromkeys(MEMBERSHIP_FUNCTIONS[var]["sets"], 0.0) if x is None else fuzzify(var, x)) for var, x in inputs.items()}
    strengths = dict.fromkeys(LEVELS, 0.0)
    activations = []
    for rid, text, level, fn in RULES:
        s = round(float(fn(mu)), 4)
        if s > 0:
            activations.append({"rule": rid, "if": text, "then": level, "strength": s})
            strengths[level] = max(strengths[level], s)
    total = sum(strengths.values())
    if total == 0:
        level, crisp = "Low", LEVEL_CENTROIDS["Low"]
    else:
        # strongest support wins; ties resolved towards the more severe level
        level = max(LEVELS, key=lambda lv: (strengths[lv], LEVEL_RANK[lv]))
        crisp = sum(strengths[lv] * LEVEL_CENTROIDS[lv] for lv in LEVELS) / total
    floor_applied = None
    if floor and LEVEL_RANK[floor] > LEVEL_RANK[level]:
        floor_applied = f"Policy floor for this notification type raised {level} → {floor}"
        level = floor
    return FuzzyResult(level, round(crisp, 2), inputs, mu, activations, {k: round(v, 4) for k, v in strengths.items()}, floor_applied)


def membership_curves(points: int = 61) -> dict[str, Any]:
    """Sampled membership curves for charting in the UI."""
    out: dict[str, Any] = {}
    for var, spec in MEMBERSHIP_FUNCTIONS.items():
        lo, hi = spec["range"]
        xs = [lo + (hi - lo) * i / (points - 1) for i in range(points)]
        rows = []
        for x in xs:
            row = {"x": round(x, 3)}
            row.update(fuzzify(var, x))
            rows.append(row)
        out[var] = {"label": spec["label"], "sets": list(spec["sets"].keys()), "points": rows}
    return out
