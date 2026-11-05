"""Print the agent's AI techniques and their results in the terminal — no website needed.

Run from the project root with ``python run.py --console`` (or F5 → "Show AI outputs in the terminal").
It works on a *temporary copy* of the database, so your real data is never changed.
The same output is saved to ``outputs/ai_outputs.txt`` for your report.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
REAL_DB = BACKEND / "data" / "library.db"

# --- isolate everything in a temporary folder BEFORE importing the app -------------------------
_TMP = Path(tempfile.mkdtemp(prefix="library-console-"))
os.environ["LIBRARY_DATA_DIR"] = str(_TMP)
os.environ["LIBRARY_DB_URL"] = f"sqlite:///{(_TMP / 'library.db').as_posix()}"
os.environ.setdefault("LIBRARY_SECRET", "console-demo")
os.environ["LIBRARY_CONSOLE_LOG"] = "0"

if os.name == "nt":
    os.system("")  # ANSI colours on Windows

BOLD, DIM, RESET, CYAN, YELLOW, GREEN, RED = "\033[1m", "\033[2m", "\033[0m", "\033[36m", "\033[33m", "\033[32m", "\033[91m"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_lines: list[str] = []


def out(text: str = "") -> None:
    _lines.append(_ANSI.sub("", text))
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode(), flush=True)


def section(n: int, title: str, concept: str) -> None:
    out()
    out(f"{BOLD}{CYAN}{'═' * 78}{RESET}")
    out(f"{BOLD}{CYAN} {n}. {title}{RESET}")
    out(f"{DIM} AI concept: {concept}{RESET}")
    out(f"{BOLD}{CYAN}{'═' * 78}{RESET}")


def table(headers: list[str], rows: list[list[object]], align: str | None = None) -> None:
    cells = [[str(h) for h in headers]] + [[str(c) for c in r] for r in rows]
    visible = lambda c: len(_ANSI.sub("", c))  # noqa: E731 — colour codes take no screen space
    widths = [max(visible(r[i]) for r in cells) for i in range(len(headers))]
    align = align or "l" * len(headers)

    def pad(c: str, w: int, a: str) -> str:
        gap = " " * (w - visible(c))
        return gap + c if a == "r" else c + gap

    def fmt(r: list[str]) -> str:
        return " │ ".join(pad(c, w, a) for c, w, a in zip(r, widths, align, strict=True))

    out(" " + BOLD + fmt(cells[0]) + RESET)
    out(" " + "─┼─".join("─" * w for w in widths))
    for r in cells[1:]:
        out(" " + fmt(r))


def prepare_database() -> None:
    if not REAL_DB.exists():
        sys.exit("No database yet — start the app once with `python run.py` (it seeds the demo data), then run this again.")
    src = sqlite3.connect(REAL_DB)
    dst = sqlite3.connect(_TMP / "library.db")
    src.backup(dst)  # consistent snapshot even if the website is running
    src.close()
    dst.close()


def main() -> None:  # noqa: C901 — a linear script of demo sections
    started = time.perf_counter()
    prepare_database()

    from sqlalchemy import func, select

    from . import db as dbm
    from .models import Copy, Notification, User
    from .services import demo, fuzzy, ml
    from .services.agent import run_cycle
    from .services.fines import FinePolicy, Slab, compute_lost_fine, compute_overdue_fine
    from .services.inference import RuleSpec, explain_chain, forward_chain
    from .services.knowledge_base import DEFAULT_RULES, validate_rule
    from .services.notifier import SentRecord, SpamGuard
    from .services.priority import NotificationQueue, PriorityInputs, choose_channel, prioritise
    from .services.settings import DEFAULTS, today

    db = dbm.SessionLocal()
    weights = DEFAULTS["priority_weights"]
    sim_today = today(db)

    out(f"{BOLD}Intelligent Library Circulation, Fine Calculation and Priority Notification Agent{RESET}")
    out(f"{DIM}Terminal output of every AI technique · simulated date {sim_today} · working on a temporary copy of the database{RESET}")

    # 1 ── PEAS ------------------------------------------------------------------------------------
    section(1, "The agent (PEAS)", "intelligent agent · task environment")
    table(["", "Description"], [
        ["Performance", "fewer/shorter overdues · fast turnover of reserved books · exact fines · low spam · no prediction-based penalties"],
        ["Environment", "books & copies · members · loans · reservations · fines · policies · holidays · librarians · calendar"],
        ["Actuators", "notifications · fine updates · copy allocation · approval requests · recommendations · logs"],
        ["Sensors", "loan/reservation/fine records · member history · ML late-return risk (advisory)"],
    ])
    out(f" Environment: {BOLD}partially observable, stochastic, sequential, dynamic, discrete, multi-agent{RESET}")

    # 2 ── Fine engine -------------------------------------------------------------------------------
    section(2, "Deterministic fine calculation", "rule-based procedure (no machine learning)")
    policy = FinePolicy((Slab(1, 7, 2), Slab(8, 14, 5), Slab(15, None, 10)), grace_days=2, max_fine=300, exclude_sundays=True, lost_processing_fee=100)
    due, returned = date(2026, 11, 4), date(2026, 11, 22)
    holiday = date(2026, 11, 9)
    r = compute_overdue_fine(due, returned, policy, [holiday])
    out(f" Student policy: grace 2 days · ₹2/day (days 1-7) · ₹5/day (8-14) · ₹10/day (15+) · cap ₹300 · Sundays free · holiday {holiday}")
    out(f" Due {due} · returned {returned}")
    table(["Date", "Day", "Treatment", "Chargeable #", "Charge", "Running total"],
          [[ln.date, ln.overdue_day, ln.note, ln.chargeable_index or "—", f"₹{ln.amount:g}", f"₹{ln.cumulative:g}"] for ln in r.lines], "lrlrrr")
    out(f" {GREEN}{BOLD}Result: {r.summary}{RESET}")
    lost = compute_lost_fine(due, date(2026, 12, 20), policy, replacement_cost=650)
    out(f" Lost-book example: {lost.summary}")

    # 3 ── Forward chaining --------------------------------------------------------------------------
    section(3, "Forward-chaining inference", "rule-based expert system · conflict resolution by salience · refraction")
    facts = {"days_overdue": 3, "days_past_grace": 1, "days_until_due": -3, "reservation_queue": 2, "renewals_left": 1, "fine_amount": 2,
             "lost_after_days": 30, "predicted_risk": 0.71, "member_late_rate": 0.4, "member_unpaid_fines": 120, "member_type": "student"}
    out(" Working memory (facts perceived for one loan):")
    out("   " + ", ".join(f"{k}={v}" for k, v in facts.items()))
    memory = {("loan", 1): dict(facts)}
    trace = forward_chain(memory, [RuleSpec.from_obj(x) for x in DEFAULT_RULES])
    table(["Iter", "Rule", "IF (matched facts)", "THEN assert"],
          [[f.iteration, f.rule_code, " AND ".join(m["condition"] for m in f.matched), f.asserted] for f in trace], "rlll")
    frame = memory[("loan", 1)]
    out(f" R12 (plain overdue notice) fired? {BOLD}{'yes' if frame.get('NOTIFY_OVERDUE') else 'no'}{RESET} — blocked because it needs HIGH_RECALL_PRIORITY to be false")
    chain = explain_chain(frame, "NOTIFY_RECALL", trace, "loan", 1)
    out(f" {GREEN}{BOLD}Why NOTIFY_RECALL? " + " → ".join(c["rule_code"] for c in chain) + RESET)

    # 4 ── Fuzzy logic --------------------------------------------------------------------------------
    section(4, "Fuzzy-logic priority level", "fuzzification · Mamdani rules (AND=min, OR=max) · defuzzification")
    fz = fuzzy.classify(lateness=7, demand=3, fine=10, risk=0.4)
    out(" Inputs: lateness = 7 days overdue · demand = 3 waiting · fine = ₹10 · risk = 0.40")
    rows = []
    for var, sets in fz.memberships.items():
        rows.append([var, ", ".join(f"{k}={v:.2f}" for k, v in sets.items() if v > 0) or "all 0"])
    table(["Variable", "Non-zero memberships μ"], rows)
    table(["Fuzzy rule", "Strength", "→ Level"], [[f"{a['rule']}: IF {a['if']}", f"{a['strength']:.2f}", a["then"]] for a in fz.activations], "lrl")
    out(f" Aggregated: " + ", ".join(f"{k} {v:.2f}" for k, v in fz.output_strengths.items()))
    out(f" {GREEN}{BOLD}Level = {fz.level}  (defuzzified crisp value {fz.crisp}){RESET}")

    # 5 ── Utility score ------------------------------------------------------------------------------
    section(5, "Weighted utility score (0-100)", "utility-based agent · multi-attribute utility")
    inputs = PriorityInputs("recall", days_overdue=7, days_until_due=0, demand=3, fine_amount=10, risk=0.4, late_rate=0.35)
    decision = prioritise(inputs, weights)
    table(["Factor", "Raw", "Normalised", "Weight", "Points"],
          [[b["label"], b["raw"], f"{b['normalised']:.2f}", f"{b['weight']:.0f}", f"{b['contribution']:.2f}"] for b in decision.breakdown], "llrrr")
    out(f" {GREEN}{BOLD}Score = {decision.score}/100 · fuzzy level = {decision.level}{RESET}")
    for level, pref in (("Critical", "email"), ("High", "sms"), ("Medium", "sms")):
        ch, why = choose_channel(level, pref)
        out(f" Channel for {level:<8} (member prefers {pref:<5}) → {ch:<6} {DIM}{why}{RESET}")

    # 6 ── Heap priority queue -------------------------------------------------------------------------
    section(6, "Heap-based notification priority queue", "priority queue / min-heap on (−level, −score, arrival)")
    samples = [
        ("Due-soon reminder · Riya", PriorityInputs("due_soon", days_until_due=1, risk=0.2, late_rate=0.1)),
        ("Recall · Aarav (2 waiting)", PriorityInputs("recall", days_overdue=4, demand=2, fine_amount=4, risk=0.7, late_rate=0.4)),
        ("Overdue · Kabir", PriorityInputs("overdue", days_overdue=2, risk=0.3, late_rate=0.2)),
        ("Fine summary · Rohan", PriorityInputs("fine_notice", fine_amount=420, late_rate=0.6)),
        ("Overdue · Deepak (20 days)", PriorityInputs("overdue", days_overdue=20, fine_amount=150, late_rate=0.5)),
        ("Reservation ready · Meera", PriorityInputs("reservation_ready", days_until_due=3, demand=1)),
    ]
    q = NotificationQueue()
    pushed = []
    for label, inp in samples:
        d = prioritise(inp, weights)
        q.push(label, d.level, d.score)
        pushed.append([label, d.level, f"{d.score:.1f}"])
    out(" Pushed in this order:")
    table(["Candidate", "Level", "Score"], pushed, "llr")
    out(" Popped from the heap (dispatch order):")
    popped = []
    rank = 1
    while q:
        popped.append([rank, q.pop()])
        rank += 1
    table(["#", "Notification"], popped, "rl")

    # 7 ── Anti-spam -----------------------------------------------------------------------------------
    section(7, "Anti-spam guard", "constraint checking on actions")
    day = sim_today
    guard = SpamGuard([SentRecord("overdue:loan:7", 1, "Medium", day - timedelta(days=1)),
                       SentRecord("recall:loan:9", 2, "High", day - timedelta(days=1)),
                       SentRecord("a", 3, "Low", day), SentRecord("b", 3, "Low", day), SentRecord("c", 3, "Low", day)],
                      DEFAULTS["cooldown_days"], DEFAULTS["daily_limit"], day)
    cases = [("Same overdue notice again (sent yesterday)", "overdue", "overdue:loan:7", 1, "Medium"),
             ("Recall escalated High → Critical", "recall", "recall:loan:9", 2, "Critical"),
             ("4th notice today for one member", "due_soon", "due_soon:loan:11", 3, "Medium"),
             ("Critical notice for that same member", "recall", "recall:loan:12", 3, "Critical"),
             ("A brand-new notice", "due_soon", "due_soon:loan:20", 4, "Low")]
    rows = []
    for label, kind, key, mid, level in cases:
        ok, reason, _checks = guard.check(kind, key, mid, level)
        rows.append([label, f"{GREEN}SEND{RESET}" if ok else f"{RED}SUPPRESS{RESET}", reason or "passes all checks"])
    table(["Situation", "Decision", "Reason"], rows)

    # 8 ── Machine learning ----------------------------------------------------------------------------
    section(8, "Machine learning: late-return risk", "supervised classification · model comparison · no leakage")
    out(f" Training Logistic Regression and Decision Tree on a {BOLD}SYNTHETIC{RESET} dataset (4,000 rows, seed 42) + library history…")
    models = ml.train_and_compare(db, n_samples=4000, seed=42, include_history=True)
    db.commit()
    table(["Model", "Accuracy", "Precision", "Recall", "F1", "ROC AUC", "Selected"],
          [[ml_name(m.algo), f"{m.metrics['accuracy']:.3f}", f"{m.metrics['precision']:.3f}", f"{m.metrics['recall']:.3f}", f"{m.metrics['f1']:.3f}",
            f"{m.metrics['roc_auc']:.3f}", "✔" if m.is_selected else ""] for m in models], "lrrrrrl")
    for m in models:
        cm = m.metrics["confusion_matrix"]
        out(f" {ml_name(m.algo)} confusion matrix:   pred on-time  pred late")
        out(f"   actual on-time   {cm['tn']:>10}  {cm['fp']:>9}")
        out(f"   actual late      {cm['fn']:>10}  {cm['tp']:>9}")
        out("   top features: " + ", ".join(f"{f['feature']} ({f['importance']:.0%})" for f in m.feature_importance[:4]))
    out(f" Excluded (sensitive): {', '.join(ml.EXCLUDED_SENSITIVE)}")
    example = {"prior_loans": 10, "prior_late_rate": 0.6, "unpaid_fines": 200, "active_loans": 3, "title_demand": 2, "loan_days": 14,
               "exam_period": 1, "weekend_checkout": 0, "member_type": "student", "category": "Mathematics"}
    pred = ml.predict(db, example)
    if pred:
        out(f" Example checkout → {BOLD}{pred['probability']:.0%} late-return risk ({pred['label']}){RESET} using {ml_name(pred['model']['algo'])}. Main factors:")
        for f in pred["factors"][:5]:
            extra = f" ({f['effect']} {abs(f['contribution']):.2f})" if "contribution" in f else (f" → {f['risk_after_step']:.0%} late" if "risk_after_step" in f else "")
            out(f"   • {f['text']}{extra}")
        out(f" {YELLOW}Decision support only: it can make a reminder earlier — it never sets a fine or a penalty.{RESET}")

    # 9 ── Fairness guard ------------------------------------------------------------------------------
    section(9, "Fairness guard on the knowledge base", "responsible AI · taint analysis over the rule graph")
    bad = {"code": "R99_UNFAIR", "name": "Restrict risky borrowers", "entity": "loan", "conclusion": "RECOMMEND_RESTRICTION",
           "conditions": [{"field": "predicted_risk", "op": ">=", "value": 0.8}], "salience": 50, "enabled": True}
    errs = validate_rule(bad, DEFAULT_RULES)
    out(" Trying to add:  IF predicted_risk >= 0.8 THEN RECOMMEND_RESTRICTION")
    out(f" {RED}{BOLD}REJECTED:{RESET} {errs[0] if errs else 'no error?!'}")

    # 10 ── One full agent cycle -----------------------------------------------------------------------
    section(10, "One full sense → think → act cycle on the library data", "agent loop")
    before_note = db.scalar(select(func.max(Notification.id))) or 0
    cycle = run_cycle(db, "console")
    db.commit()
    p = cycle.percepts
    out(f" PERCEIVE  {p['active_loans']} active loans · {p['overdue_loans']} overdue · {p['due_within_2_days']} due within 2 days · "
        f"{p['reservations_waiting']} reservations waiting · ₹{p['unpaid_fines_total']:g} unpaid")
    counts: dict[str, int] = {}
    for f in cycle.firings:
        counts[f["rule_code"]] = counts.get(f["rule_code"], 0) + 1
    out(f" THINK     {len(cycle.firings)} rule firings in {max((f['iteration'] for f in cycle.firings), default=0)} iterations: "
        + ", ".join(f"{k}×{v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:8]))
    notes = db.scalars(select(Notification).where(Notification.id > before_note).order_by(Notification.score.desc())).all()
    sent = [n for n in notes if n.status == "sent"]
    out(f" ACT       {len(sent)} notifications sent, {sum(n.status == 'suppressed' for n in notes)} suppressed, "
        f"{sum(n.status == 'queued' for n in notes)} queued · cycle took {cycle.duration_ms} ms")
    if sent:
        table(["Level", "Score", "Type", "Member", "Channel"],
              [[n.level, f"{n.score:.1f}", n.kind.replace("_", " "), n.member.name, n.channel] for n in sent[:10]], "lrlll")
    recs = [d["text"] for d in cycle.decisions if d.get("type") == "recommendation"]
    for rtext in recs[:3]:
        out(f" RECOMMEND {rtext}")

    # 11 ── Guided scenario --------------------------------------------------------------------------
    section(11, "Guided scenario: reserved book becomes overdue", "everything together, day by day")
    librarian = db.scalar(select(User).where(User.role == "librarian"))
    if db.scalar(select(Copy).where(Copy.barcode == demo.DEMO_BARCODE)) is None or librarian is None:
        out(" (demo copy not found — reset the demo data with `python run.py --reset`)")
    else:
        state = demo.start(db, librarian)
        db.commit()
        for _ in range(len(demo.STEPS) - 1):
            state = demo.next_step(db, librarian)
            db.commit()
        for entry in state["state"]["log"]:
            out(f"\n {BOLD}{YELLOW}Step {entry['step']} · {entry['sim_date']} · {entry['title']}{RESET}")
            for line in entry["narrative"]:
                out(f"   ▸ {line}")

    db.close()
    dbm.engine.dispose()
    elapsed = time.perf_counter() - started
    outputs = ROOT / "outputs"
    outputs.mkdir(exist_ok=True)
    target = outputs / "ai_outputs.txt"
    target.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    out()
    out(f"{GREEN}{BOLD}Done in {elapsed:.1f}s. Saved a copy of this output to {target}{RESET}")
    out(f"{DIM}Your real library database was not modified.{RESET}")


def ml_name(algo: str) -> str:
    return {"logistic_regression": "Logistic Regression", "decision_tree": "Decision Tree"}.get(algo, algo)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    main()
