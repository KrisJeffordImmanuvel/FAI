"""Forward-chaining production-rule inference engine.

Working memory holds one *fact frame* per entity (a loan, member, reservation
or fine), e.g. ``{"days_overdue": 5, "reservation_queue": 2}``. Each rule says

    IF  <all conditions hold on a frame of type ENTITY>
    THEN assert <CONCLUSION> = True on that frame

The engine repeatedly builds the *conflict set* (all rule/entity activations
whose conditions hold and whose conclusion is not yet asserted), orders it by
salience (conflict resolution), fires the activations and adds the new facts
to working memory. Because newly asserted facts may satisfy other rules, it
loops until a fixpoint (no new activations) — that is forward chaining.

Refraction: a fact is asserted at most once per entity, so a rule never fires
twice for the same entity. Conditions are re-checked right before firing so
a higher-salience rule can block a lower one that tests ``is_false``.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

OPERATORS: dict[str, str] = {
    "==": "equals",
    "!=": "does not equal",
    ">": "greater than",
    ">=": "at least",
    "<": "less than",
    "<=": "at most",
    "in": "is one of",
    "is_true": "is true",
    "is_false": "is false",
}


@dataclass
class Condition:
    field: str
    op: str
    value: Any = None
    value_field: str | None = None  # compare against another fact in the same frame

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Condition:
        return Condition(d["field"], d["op"], d.get("value"), d.get("value_field") or None)

    def describe(self) -> str:
        target = self.value_field if self.value_field else repr(self.value)
        if self.op in ("is_true", "is_false"):
            return f"{self.field} {OPERATORS[self.op]}"
        return f"{self.field} {self.op} {target}"


@dataclass
class RuleSpec:
    code: str
    name: str
    entity: str
    conditions: list[Condition]
    conclusion: str
    salience: int = 50
    enabled: bool = True
    description: str = ""

    @staticmethod
    def from_obj(obj: Any) -> RuleSpec:
        """Build from an ORM ``Rule`` or a plain dict."""
        get = (lambda k, d=None: obj.get(k, d)) if isinstance(obj, dict) else (lambda k, d=None: getattr(obj, k, d))
        return RuleSpec(
            code=get("code"),
            name=get("name"),
            entity=get("entity"),
            conditions=[Condition.from_dict(c) for c in (get("conditions") or [])],
            conclusion=get("conclusion"),
            salience=int(get("salience", 50) or 0),
            enabled=bool(get("enabled", True)),
            description=get("description", "") or "",
        )


@dataclass
class Firing:
    iteration: int
    rule_code: str
    rule_name: str
    entity: str
    entity_id: int
    asserted: str
    salience: int
    matched: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate(cond: Condition, frame: dict[str, Any]) -> tuple[bool, Any]:
    """Evaluate one condition; returns (holds, actual_value)."""
    actual = frame.get(cond.field)
    if cond.op == "is_true":
        return bool(actual) is True, bool(actual)
    if cond.op == "is_false":
        return not bool(actual), bool(actual)
    if actual is None:
        return False, None
    target = frame.get(cond.value_field) if cond.value_field else cond.value
    if target is None and cond.op != "!=":
        return False, actual
    try:
        if cond.op == "==":
            return actual == target, actual
        if cond.op == "!=":
            return actual != target, actual
        if cond.op == ">":
            return actual > target, actual
        if cond.op == ">=":
            return actual >= target, actual
        if cond.op == "<":
            return actual < target, actual
        if cond.op == "<=":
            return actual <= target, actual
        if cond.op == "in":
            options = target if isinstance(target, (list, tuple, set)) else [x.strip() for x in str(target).split(",")]
            return actual in options, actual
    except TypeError:
        return False, actual
    raise ValueError(f"Unknown operator {cond.op!r}")


def _match(rule: RuleSpec, frame: dict[str, Any]) -> list[dict[str, Any]] | None:
    matched: list[dict[str, Any]] = []
    for cond in rule.conditions:
        ok, actual = evaluate(cond, frame)
        if not ok:
            return None
        entry = {"condition": cond.describe(), "field": cond.field, "actual": actual}
        if cond.value_field:
            entry["compared_to"] = {cond.value_field: frame.get(cond.value_field)}
        matched.append(entry)
    return matched


WorkingMemory = dict[tuple[str, int], dict[str, Any]]


def forward_chain(
    memory: WorkingMemory,
    rules: Iterable[RuleSpec],
    max_iterations: int = 25,
) -> list[Firing]:
    """Run inference to a fixpoint, mutating ``memory``. Returns the firing trace."""
    active = sorted((r for r in rules if r.enabled), key=lambda r: (-r.salience, r.code))
    by_entity: dict[str, list[tuple[tuple[str, int], dict[str, Any]]]] = {}
    for key, frame in memory.items():
        by_entity.setdefault(key[0], []).append((key, frame))

    trace: list[Firing] = []
    for iteration in range(1, max_iterations + 1):
        conflict_set: list[tuple[RuleSpec, tuple[str, int]]] = []
        for rule in active:
            for key, frame in by_entity.get(rule.entity, []):
                if frame.get(rule.conclusion):
                    continue  # refraction
                if _match(rule, frame) is not None:
                    conflict_set.append((rule, key))
        if not conflict_set:
            break
        fired_any = False
        for rule, key in conflict_set:  # already in salience order
            frame = memory[key]
            if frame.get(rule.conclusion):
                continue
            matched = _match(rule, frame)  # re-check: earlier firings may have changed the frame
            if matched is None:
                continue
            frame[rule.conclusion] = True
            frame.setdefault("_because", {})[rule.conclusion] = rule.code
            trace.append(
                Firing(iteration, rule.code, rule.name, key[0], key[1], rule.conclusion, rule.salience, matched)
            )
            fired_any = True
        if not fired_any:
            break
    return trace


def explain_chain(frame: dict[str, Any], fact: str, trace: Sequence[Firing], entity: str, entity_id: int) -> list[dict[str, Any]]:
    """Return the firings (in order) that led to ``fact`` on one entity — a proof tree, flattened."""
    relevant = [f for f in trace if f.entity == entity and f.entity_id == entity_id]
    by_fact = {f.asserted: f for f in relevant}
    needed: list[Firing] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen or name not in by_fact:
            return
        seen.add(name)
        firing = by_fact[name]
        for m in firing.matched:
            visit(m["field"])
        needed.append(firing)

    visit(fact)
    return [f.to_dict() for f in needed]
