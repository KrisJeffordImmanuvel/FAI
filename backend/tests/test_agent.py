"""Sense-think-act cycle, approvals (human oversight), KB API, ML and the full demo scenario."""
from sqlalchemy import select

from app.models import AgentCycle, Approval, Loan, Notification
from app.services import ml


def test_run_cycle_records_percepts_rules_actions(client, lib_h, session):
    r = client.post("/api/agent/run", headers=lib_h, json={"mode": "manual"})
    assert r.status_code == 200
    cyc = client.get(f"/api/agent/cycles/{r.json()['id']}", headers=lib_h).json()
    assert cyc["percepts"]["active_loans"] > 0
    assert cyc["firings"] and cyc["decisions"] and cyc["events"]
    phases = {e["phase"] for e in cyc["events"]}
    assert {"perceive", "think", "act"} <= phases
    # the seeder guarantees overdue + reserved loans → recalls
    assert any(f["asserted"] == "HIGH_RECALL_PRIORITY" for f in cyc["firings"])


def test_notifications_have_explanations(client, lib_h):
    client.post("/api/agent/run", headers=lib_h, json={})
    items = client.get("/api/notifications?status=delivered", headers=lib_h).json()["items"]
    n = client.get(f"/api/notifications/{items[0]['id']}", headers=lib_h).json()
    exp = n["explanation"]
    assert exp["priority"]["breakdown"] and exp["priority"]["fuzzy"]["memberships"]
    assert exp["channel"]["reason"] and exp["anti_spam"]


def test_second_cycle_same_day_suppresses_duplicates(client, lib_h, session):
    client.post("/api/agent/run", headers=lib_h, json={})
    before = session.scalar(select(Notification.id).order_by(Notification.id.desc()))
    client.post("/api/agent/run", headers=lib_h, json={})
    session.expire_all()
    new = session.scalars(select(Notification).where(Notification.id > before)).all()
    assert new and all(n.status != "sent" or n.level == "Critical" for n in new)


def test_queue_preview_is_heap_ordered(client, lib_h):
    q = client.get("/api/notifications/queue", headers=lib_h).json()["items"]
    rank = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}
    keys = [(rank[i["level"]], i["score"]) for i in q]
    assert keys == sorted(keys, reverse=True)


def test_prediction_never_sets_fine_and_lost_needs_approval(client, lib_h, session):
    client.post("/api/agent/run", headers=lib_h, json={})
    session.expire_all()
    appr = session.scalar(select(Approval).where(Approval.kind == "mark_lost", Approval.status == "pending"))
    assert appr is not None
    loan = session.get(Loan, appr.loan_id)
    assert loan.status == "active"  # the agent did NOT mark it lost by itself
    r = client.post(f"/api/approvals/{appr.id}/decide", headers=lib_h, json={"approve": False, "note": ""})
    assert r.status_code == 400  # rejection needs a note
    r = client.post(f"/api/approvals/{appr.id}/decide", headers=lib_h, json={"approve": True, "note": "Member confirmed the book is lost"})
    assert r.status_code == 200
    session.expire_all()
    loan = session.get(Loan, appr.loan_id)
    assert loan.status == "lost" and loan.fine.kind == "lost"
    assert loan.fine.amount >= loan.copy.book.price


def test_advance_clock_runs_cycles(client, lib_h):
    status = client.get("/api/agent/status", headers=lib_h).json()
    r = client.post("/api/agent/advance", headers=lib_h, json={"days": 3, "run_agent": True})
    assert r.status_code == 200 and len(r.json()["cycles"]) == 3
    assert r.json()["status"]["sim_date"] > status["sim_date"]


def test_kb_editor_api_and_fairness_guard(client, admin_h, lib_h):
    bad = {"code": "R90_BAD", "name": "Restrict risky members", "entity": "loan", "conclusion": "RECOMMEND_MARK_LOST",
           "conditions": [{"field": "predicted_risk", "op": ">=", "value": 0.9}], "salience": 50, "enabled": True}
    r = client.post("/api/kb/rules", headers=admin_h, json=bad)
    assert r.status_code == 422 and "Fairness" in str(r.json())
    good = dict(bad, code="R90_GOOD", name="Overdue a month", conclusion="ESCALATE_TO_LIBRARIAN",
                conditions=[{"field": "days_overdue", "op": ">=", "value": 30}])
    r = client.post("/api/kb/rules", headers=admin_h, json=good)
    assert r.status_code == 201
    t = client.post("/api/kb/test", headers=lib_h, json={"entity": "loan", "facts": {"days_overdue": 31, "reservation_queue": 1, "days_until_due": -31, "lost_after_days": 30}})
    assert "ESCALATE_TO_LIBRARIAN" in t.json()["asserted"] and "NOTIFY_RECALL" in t.json()["actions"]


def test_ml_dataset_no_leakage_or_sensitive_features():
    rows = ml.generate_dataset(200, seed=1)
    assert rows == ml.generate_dataset(200, seed=1)  # reproducible
    forbidden = {"gender", "age", "religion", "caste", "address", "name", "returned_on", "renewals", "fine_amount", "days_late"}
    assert not forbidden & set(ml.FEATURES)
    assert all(r["synthetic"] for r in rows)


def test_ml_summary_retrain_and_predict(client, admin_h, lib_h):
    s = client.get("/api/ml/summary", headers=lib_h).json()
    assert {m["algo"] for m in s["latest"]} == {"logistic_regression", "decision_tree"}
    for m in s["latest"]:
        assert {"accuracy", "precision", "recall", "f1", "confusion_matrix"} <= set(m["metrics"])
        assert m["feature_importance"]
    r = client.post("/api/ml/retrain", headers=admin_h, json={"n_samples": 1500, "seed": 3, "include_history": True})
    assert r.status_code == 200 and len(r.json()["models"]) == 2
    lr = next(m for m in r.json()["models"] if m["algo"] == "logistic_regression")
    client.post(f"/api/ml/models/{lr['id']}/select", headers=admin_h)
    p = client.post("/api/ml/predict", headers=lib_h, json={"prior_loans": 10, "prior_late_rate": 0.6, "unpaid_fines": 200, "active_loans": 3,
                                                           "title_demand": 2, "loan_days": 14, "exam_period": 1, "weekend_checkout": 0,
                                                           "member_type": "student", "category": "Mathematics"}).json()
    assert 0 <= p["probability"] <= 1 and p["factors"] and p["model"]["algo"] == "logistic_regression"


def test_full_guided_demo_scenario(client, lib_h, member_h, session):
    r = client.post("/api/demo/start", headers=lib_h)
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    loan_id, res_id = state["loan_id"], state["reservation_id"]
    for _ in range(5):
        r = client.post("/api/demo/next", headers=lib_h)
        assert r.status_code == 200, r.text
    data = r.json()
    assert data["state"]["step"] == 5
    log = data["state"]["log"]
    assert len(log) == 6 and all(entry["narrative"] for entry in log)

    session.expire_all()
    notes = session.scalars(select(Notification).where(Notification.loan_id == loan_id).order_by(Notification.id)).all()
    kinds = [(n.kind, n.status, n.level) for n in notes]
    assert any(k == "due_soon" and s == "sent" for k, s, _ in kinds)
    assert any(k == "due_soon" and s == "suppressed" for k, s, _ in kinds), kinds  # duplicate suppressed
    recalls = [(s, lv) for k, s, lv in kinds if k == "recall" and s in ("sent", "read")]
    assert recalls and recalls[0][1] == "High"
    assert any(lv == "Critical" for _, lv in recalls), kinds  # priority escalated
    loan = session.get(Loan, loan_id)
    assert loan.status == "returned" and loan.fine is not None
    assert loan.fine.status == "partially_paid"
    assert any(ln["status"] == "holiday" for ln in loan.fine.breakdown["lines"])  # demo holiday excluded
    from app.models import Reservation

    res = session.get(Reservation, res_id)
    assert res.status == "fulfilled"
    ready_notes = session.scalars(select(Notification).where(Notification.reservation_id == res_id, Notification.kind == "reservation_ready")).all()
    assert ready_notes and ready_notes[0].status in ("sent", "read")
    # the member (Aarav) sees the recall in their inbox
    inbox = client.get("/api/notifications", headers=member_h).json()["items"]
    assert any(n["kind"] == "recall" for n in inbox)
    assert session.scalar(select(AgentCycle).where(AgentCycle.mode == "demo")) is not None
