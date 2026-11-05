"""Utility scoring, fuzzy logic, heap queue ordering and channel choice."""
from app.services import fuzzy
from app.services.priority import NotificationQueue, PriorityInputs, choose_channel, prioritise, utility_score

W = {"urgency": 25, "overdue": 20, "demand": 20, "fine": 10, "risk": 15, "history": 10}


def test_utility_breakdown_sums_to_score():
    score, breakdown = utility_score(PriorityInputs("recall", days_overdue=15, demand=2, fine_amount=100, risk=0.5, late_rate=0.2), W)
    assert round(sum(b["contribution"] for b in breakdown), 2) == score
    # 25*1 + 20*0.5 + 20*0.4 + 10*0.2 + 15*0.5 + 10*0.2 = 54.5
    assert score == 54.5


def test_weights_are_normalised_to_100():
    s1, _ = utility_score(PriorityInputs("recall", days_overdue=30, demand=5, fine_amount=500, risk=1, late_rate=1), W)
    s2, _ = utility_score(PriorityInputs("recall", days_overdue=30, demand=5, fine_amount=500, risk=1, late_rate=1), {k: v * 3 for k, v in W.items()})
    assert s1 == s2 == 100.0


def test_score_is_bounded_and_monotonic_in_overdue():
    scores = [utility_score(PriorityInputs("overdue", days_overdue=d), W)[0] for d in (0, 5, 10, 40)]
    assert scores == sorted(scores)
    assert 0 <= scores[0] and scores[-1] <= 100


def test_membership_functions():
    mu = fuzzy.fuzzify("lateness", 3)
    assert mu["slightly_overdue"] == 1.0 and mu["severely_overdue"] == 0
    mu = fuzzy.fuzzify("lateness", 25)
    assert mu["severely_overdue"] == 1.0
    mu = fuzzy.fuzzify("demand", 3)
    assert mu["high"] == 0.5 and mu["medium"] == 0.0
    assert all(0 <= v <= 1 for var in fuzzy.MEMBERSHIP_FUNCTIONS for x in range(-5, 30) for v in fuzzy.fuzzify(var, x).values())


def test_fuzzy_levels():
    assert fuzzy.classify(-6, 0, 0, 0.1).level == "Low"
    assert fuzzy.classify(-1, 0, 0, 0.9).level == "Medium"  # due soon + high risk
    assert fuzzy.classify(3, 0, 0, 0.2).level == "Medium"  # slightly overdue, low demand
    assert fuzzy.classify(3, 2, 0, 0.2).level == "High"  # slightly overdue, medium demand
    assert fuzzy.classify(10, 4, 0, 0.2).level == "Critical"  # moderately overdue + high demand
    assert fuzzy.classify(25, 0, 0, 0.2).level == "Critical"  # severely overdue
    assert fuzzy.classify(0, 0, 450, 0.1).level == "High"  # large fine


def test_fuzzy_explains_activations_and_crisp_value():
    r = fuzzy.classify(7, 3, 20, 0.3)
    assert r.activations and all(a["strength"] > 0 for a in r.activations)
    assert 0 <= r.crisp <= 100
    assert r.output_strengths[r.level] == max(r.output_strengths.values())


def test_kind_floor_applied():
    d = prioritise(PriorityInputs("recall", days_overdue=1, demand=0), W)  # fuzzy alone says Medium
    assert fuzzy.LEVEL_RANK[d.level] >= fuzzy.LEVEL_RANK["High"]
    assert d.fuzzy["floor_applied"]


def test_heap_orders_by_level_then_score_then_fifo():
    q = NotificationQueue()
    q.push("low-99", "Low", 99)
    q.push("high-40", "High", 40)
    q.push("crit-10", "Critical", 10)
    q.push("high-70", "High", 70)
    q.push("high-70b", "High", 70)
    assert q.snapshot() == ["crit-10", "high-70", "high-70b", "high-40", "low-99"]
    assert [q.pop() for _ in range(len(q))] == ["crit-10", "high-70", "high-70b", "high-40", "low-99"]


def test_channel_selection():
    assert choose_channel("Critical", "sms")[0] == "sms"
    assert choose_channel("Critical", "email")[0] == "sms"
    assert choose_channel("Critical", "in_app")[0] == "email"
    assert choose_channel("High", "email")[0] == "email"
    assert choose_channel("High", "in_app")[0] == "in_app"
    assert choose_channel("Medium", "sms")[0] == "in_app"
    assert choose_channel("Low", "email")[0] == "in_app"


def test_lateness_not_applicable_for_fine_summaries():
    d = prioritise(PriorityInputs("fine_notice", fine_amount=450), W)
    assert d.fuzzy["inputs"]["lateness"] is None
    assert all(v == 0 for v in d.fuzzy["memberships"]["lateness"].values())
    assert d.level == "High"  # driven by "fine is large" only
