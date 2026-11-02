"""Forward-chaining inference engine and knowledge-base validation."""
from app.services.inference import RuleSpec, explain_chain, forward_chain
from app.services.knowledge_base import DEFAULT_RULES, fairness_violations, tainted_facts, validate_rule


def rules():
    return [RuleSpec.from_obj(r) for r in DEFAULT_RULES]


def loan(**kw):
    base = {"days_overdue": 0, "days_past_grace": 0, "days_until_due": 5, "reservation_queue": 0, "renewals_left": 1,
            "fine_amount": 0, "lost_after_days": 30, "predicted_risk": 0.2, "member_late_rate": 0.1, "member_unpaid_fines": 0, "member_type": "student"}
    base.update(kw)
    return base


def test_overdue_and_reserved_chains_to_recall():
    mem = {("loan", 1): loan(days_overdue=3, days_past_grace=1, days_until_due=-3, reservation_queue=2)}
    trace = forward_chain(mem, rules())
    f = mem[("loan", 1)]
    assert f["OVERDUE"] and f["IN_DEMAND"] and f["HIGH_RECALL_PRIORITY"] and f["NOTIFY_RECALL"]
    # R12 requires HIGH_RECALL_PRIORITY to be false → must not fire
    assert not f.get("NOTIFY_OVERDUE")
    # chaining needs more than one iteration
    by_fact = {t.asserted: t for t in trace}
    assert by_fact["HIGH_RECALL_PRIORITY"].iteration > by_fact["OVERDUE"].iteration
    assert by_fact["NOTIFY_RECALL"].iteration > by_fact["HIGH_RECALL_PRIORITY"].iteration


def test_overdue_without_demand_sends_plain_overdue_notice():
    mem = {("loan", 1): loan(days_overdue=2, days_until_due=-2)}
    forward_chain(mem, rules())
    f = mem[("loan", 1)]
    assert f["NOTIFY_OVERDUE"] and not f.get("HIGH_RECALL_PRIORITY")


def test_refraction_each_fact_once():
    mem = {("loan", 1): loan(days_overdue=20, days_past_grace=18, days_until_due=-20, reservation_queue=1)}
    trace = forward_chain(mem, rules())
    asserted = [t.asserted for t in trace]
    assert len(asserted) == len(set(asserted))


def test_value_field_comparison_for_lost_candidate():
    mem = {("loan", 1): loan(days_overdue=31, days_until_due=-31, lost_after_days=30)}
    forward_chain(mem, rules())
    assert mem[("loan", 1)]["RECOMMEND_MARK_LOST"]
    mem = {("loan", 2): loan(days_overdue=29, days_until_due=-29, lost_after_days=30)}
    forward_chain(mem, rules())
    assert not mem[("loan", 2)].get("RECOMMEND_MARK_LOST")


def test_disabled_rule_does_not_fire():
    rs = rules()
    for r in rs:
        if r.code == "R04_HIGH_RECALL":
            r.enabled = False
    mem = {("loan", 1): loan(days_overdue=3, days_until_due=-3, reservation_queue=1)}
    forward_chain(mem, rs)
    assert not mem[("loan", 1)].get("HIGH_RECALL_PRIORITY")
    assert mem[("loan", 1)]["NOTIFY_OVERDUE"]


def test_due_soon_and_entity_scoping():
    mem = {("loan", 1): loan(days_until_due=1), ("member", 1): {"unpaid_fines": 150, "overdue_loans": 0, "fine_notice_threshold": 100,
                                                               "restriction_threshold": 250, "status": "active", "late_rate": 0, "active_loans": 1}}
    forward_chain(mem, rules())
    assert mem[("loan", 1)]["NOTIFY_DUE_SOON"]
    assert mem[("member", 1)]["NOTIFY_FINE"]
    assert not mem[("member", 1)].get("RECOMMEND_RESTRICTION")


def test_explain_chain_returns_supporting_firings_in_order():
    mem = {("loan", 7): loan(days_overdue=3, days_until_due=-3, reservation_queue=1)}
    trace = forward_chain(mem, rules())
    chain = explain_chain(mem[("loan", 7)], "NOTIFY_RECALL", trace, "loan", 7)
    codes = [c["rule_code"] for c in chain]
    assert codes[-1] == "R13_NOTIFY_RECALL"
    assert "R04_HIGH_RECALL" in codes and "R01_OVERDUE" in codes and "R03_IN_DEMAND" in codes
    assert codes.index("R01_OVERDUE") < codes.index("R04_HIGH_RECALL")


def test_rule_validation():
    good = {"code": "R99_TEST", "name": "Test rule", "entity": "loan", "conclusion": "NOTIFY_OVERDUE",
            "conditions": [{"field": "days_overdue", "op": ">", "value": 3}]}
    assert validate_rule(good, DEFAULT_RULES) == []
    bad = dict(good, conditions=[{"field": "nope", "op": ">", "value": 1}])
    assert validate_rule(bad, DEFAULT_RULES)
    missing_value = dict(good, conditions=[{"field": "days_overdue", "op": ">"}])
    assert validate_rule(missing_value, DEFAULT_RULES)


def test_fairness_guard_blocks_prediction_based_penalties():
    assert fairness_violations(DEFAULT_RULES) == []
    direct = {"code": "R98_BAD", "name": "Punish risky", "entity": "loan", "conclusion": "RECOMMEND_MARK_LOST",
              "conditions": [{"field": "predicted_risk", "op": ">=", "value": 0.8}]}
    assert any("Fairness guard" in e for e in validate_rule(direct, DEFAULT_RULES))
    # indirect: HIGH_RISK_BORROWER is derived from predicted_risk (rule R07)
    indirect = dict(direct, code="R97_BAD", conditions=[{"field": "HIGH_RISK_BORROWER", "op": "is_true"}])
    assert "HIGH_RISK_BORROWER" in tainted_facts(DEFAULT_RULES)
    assert any("Fairness guard" in e for e in validate_rule(indirect, DEFAULT_RULES))
