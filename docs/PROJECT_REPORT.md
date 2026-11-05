# Project Report — Intelligent Library Circulation, Fine Calculation and Priority Notification Agent

*Fundamentals of Artificial Intelligence · Microproject*

---

## 1. Problem statement

College libraries lose a lot of value to circulation friction:

- Popular books stay overdue while other students wait.
- Fines are calculated by hand, inconsistently and without clear explanations.
- Reminder messages are either missing or so frequent that members ignore them.
- Librarians have no early warning about which loans are likely to come back late.

Most library software is passive CRUD: it stores records but does not *reason* about them.

The goal of this project is an **intelligent agent** that continuously monitors circulation and decides what needs attention and how urgently. It acts on those decisions (fines, notifications, allocations, recommendations) and **explains every action**. High-impact decisions stay under human control.

## 2. Objectives

1. Model the system formally as an AI agent (**PEAS**, environment classification, sense-think-act loop).
2. Encode library knowledge as an **editable rule base** and reason over it with **forward chaining**.
3. Calculate fines **deterministically** with slabs, grace periods, holidays, caps, lost-book handling, partial payments and audited waivers. Produce an itemised day-by-day explanation.
4. Prioritise notifications with a transparent **weighted utility function**, **fuzzy logic** levels and a **heap priority queue**, while preventing spam.
5. Predict **late-return risk** with machine learning (Logistic Regression vs Decision Tree) without data leakage or sensitive attributes, and use it **only as decision support**.
6. Provide **human oversight** for waivers, restrictions and lost-book declarations.
7. Make the agent demonstrable with a **simulated clock** and a **guided scenario**, with every decision visible in the UI.

## 3. PEAS analysis

| | Description |
|---|---|
| **Performance** | Fewer and shorter overdue loans; faster turnover of reserved books; correct, consistent and explainable fines; high notification *resolution rate* (member acts after a notice); low spam (no repeats within cooldown, daily caps); zero penalties based purely on predictions; every high-impact action approved by a human. |
| **Environment** | Titles, physical copies and their states; members and their history; loans, renewals and returns; reservation queues and holds; fines, payments, waivers; policies and holidays; librarians (approvers); the calendar. |
| **Actuators** | Create and dispatch notifications (in-app / simulated email / SMS); write and update fines; allocate copies to queues and expire holds; create approval requests; log recommendations; write the timeline and audit trail. |
| **Sensors** | Database observations each cycle: days overdue, days to due, renewals left, queue length, copies on the shelf, unpaid fines, member late-rate, hold expiry, plus the ML risk estimate attached at checkout. |

### Environment classification

| Property | Classification | Justification |
|---|---|---|
| Observability | **Partially observable** | The agent sees records, not intentions. Whether a member still has the book, has lost it, or will return it tomorrow is hidden. The ML model estimates this hidden state. |
| Determinism | **Stochastic** | Member responses to the same situation vary, and a notification does not guarantee a return. |
| Episodes | **Sequential** | Actions affect the future: cooldowns, accruing fines and changes to who is next in a queue. |
| Dynamics | **Dynamic** | Members and librarians change the world between and during cycles (returns, payments, reservations). |
| State/time | **Discrete** | Time moves in whole days, and states and actions are discrete. Fuzzy logic adds graded truth on top. |
| Agents | **Multi-agent (cooperative)** | Librarians share the goal and act as approvers; members are other actors. |
| Knowledge | **Partly known** | Policies are fully known (encoded as rules and data); behaviour is learnt from data. |

**Agent type:** a utility-based agent with a rule-based (expert-system) core and a learning component. It also has a reflex
behaviour: immediate FIFO allocation when a copy is returned.

## 4. System design

### 4.1 Architecture

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Recharts. The UI is role-based, and every chart also has a table view.
- **Backend:** FastAPI + SQLAlchemy 2 + Pydantic 2. Services are kept separate from routers, and the backend serves the built frontend.
- **Database:** SQLite (WAL). Every transaction starts with `BEGIN IMMEDIATE`. Copy status changes use compare-and-set updates, and partial unique indexes guarantee one active loan per copy, one hold per copy, and one open reservation per member per title.
- **ML:** scikit-learn pipelines saved with joblib; metadata is kept in the `ml_models` table.

(See the Mermaid diagrams in `README.md`.)

### 4.2 Database schema (main tables)

| Table | Key columns |
|---|---|
| `users` | email, PBKDF2 password hash, role (admin/librarian/member), member_id |
| `members` | code, name, type, department, status (active/restricted/suspended), notify_pref |
| `policies` | per member type: max_loans, loan_days, max_renewals, max_reservations, grace_days, fine_slabs (JSON), max_fine, exclude_sundays, lost_after_days, lost_processing_fee, hold_days |
| `books` / `copies` | title metadata, replacement price / barcode, shelf, status |
| `loans` | copy, member, issued/due/returned dates, renewals, status, risk_score + risk_detail (prediction, factors, checkout features) |
| `reservations` | book, member, status (waiting/ready/fulfilled/cancelled/expired), held copy, expiry |
| `fines`, `payments`, `waivers` | amount, paid, waived, status, itemised breakdown JSON; payment method; waiver reason + approver |
| `holidays` | date, name |
| `approvals` | kind (waiver/restrict_member/mark_lost), source (agent/member/librarian), reason, explanation, decision |
| `notifications` | kind, score, level, channel, subject/body, status (sent/read/suppressed/queued), suppression reason, dedupe key, explanation JSON, outcome |
| `rules` | code, entity, conditions JSON, conclusion, salience, enabled |
| `settings` | sim clock, utility weights, cooldowns, limits, thresholds |
| `agent_cycles` / `agent_events` | per-cycle percepts, firings, decisions, actions; timeline entries |
| `ml_models`, `audit_logs` | metrics, importances, selection; who did what, when (simulated date) |

### 4.3 The agent loop (`services/agent.py`)

1. **Perceive.** Build a *fact frame* for every active loan, open reservation, active member and open fine. While doing so, the fine for each loan is evaluated by the deterministic engine.
2. **Think.** Run forward chaining over all frames. For every `NOTIFY_*` conclusion, build a candidate, score it with the utility function and classify it with fuzzy logic.
3. **Act.**
   - Persist fines.
   - Expire uncollected holds and allocate free copies.
   - Push candidates (plus any carried-over queued notices) into the heap and pop them in priority order through the anti-spam guard. Dispatch on the chosen channel, up to the cycle's capacity.
   - Create approval requests for `RECOMMEND_*` conclusions.
   - Log escalations as librarian recommendations.
4. **Record.** Store the percepts summary, all firings, per-entity decisions (facts + asserted conclusions), actions and timeline events.

Returns trigger a **reflex** action: the copy is allocated FIFO immediately, and a `reservation_ready` notification goes through the same scoring and queueing pipeline.

## 5. Algorithms

### 5.1 Forward-chaining inference (`services/inference.py`)

```
WM ← fact frames;  trace ← []
repeat (max 25 iterations):
    conflict_set ← { (rule, entity) | rule.enabled, entity.type = rule.entity,
                     rule.conclusion ∉ entity (refraction), all conditions hold }
    if conflict_set = ∅: break                     # fixpoint
    sort conflict_set by salience (desc)           # conflict resolution
    for (rule, entity) in conflict_set:
        if conditions still hold:                  # earlier firings may block is_false conditions
            entity[rule.conclusion] ← true; trace.append(rule, entity, matched facts, iteration)
```

Conditions support `== != > >= < <= in is_true is_false` and comparisons with another fact (`value_field`, e.g.
`days_overdue >= lost_after_days`). `explain_chain` rebuilds the proof tree for any conclusion.

Example chain:
`R01: days_overdue > 0 → OVERDUE` → `R03: reservation_queue ≥ 1 → IN_DEMAND`
→ `R04: OVERDUE ∧ IN_DEMAND → HIGH_RECALL_PRIORITY` → `R13 → NOTIFY_RECALL`. At the same time, `R12` (a plain overdue notice) is blocked because it requires `HIGH_RECALL_PRIORITY` to be false.

**Fairness taint analysis** (`knowledge_base.py`): compute, to a fixpoint, the set of facts whose truth can depend on
`predicted_risk`. Any rule whose penalising conclusion (`RECOMMEND_MARK_LOST`, `RECOMMEND_RESTRICTION`) is in that set is rejected, so a prediction can never lead to a penalty, even indirectly.

### 5.2 Deterministic fine engine (`services/fines.py`)

For each calendar day *n* after the due date, up to the return (or lost) date:

1. If *n* ≤ grace_days, the day is free (grace).
2. Otherwise, if the day is a library holiday or (policy) a Sunday, it is free and does not advance the slab counter.
3. Otherwise it is chargeable day *k* += 1, charged at the rate of the slab containing *k*.
4. The running total is capped at `max_fine`. The day that reaches the cap is charged partially; later days are charged ₹0.

All arithmetic is in integer paise. Lost book = capped overdue fine up to the declaration date + replacement price + processing fee.
Payments are validated against the balance (partial payments allowed, overpayment rejected). Waivers require a reason and are recorded with the approver.

*Example (student: grace 2, slabs ₹2/₹5/₹10, cap ₹300):* due Wed 4 Nov, returned Wed 11 Nov → 7 days overdue: 2 grace,
Sun 8 Nov excluded, 9 Nov holiday excluded, 3 chargeable × ₹2 = **₹6**.

### 5.3 Weighted utility score (`services/priority.py`)

score = Σ wₖ·xₖ, with the weights rescaled to sum to 100. The six factors are normalised to [0, 1]:

| Factor | Normalisation | Default weight |
|---|---|---|
| Urgency of notice type | recall 1.0, overdue 0.8, reservation ready 0.7, pickup 0.65, fine 0.5, due soon 0.45, early 0.3 | 25 |
| Days overdue | min(d/30, 1) | 20 |
| Reservation demand | min(q/5, 1) | 20 |
| Fine amount | min(₹/500, 1) | 10 |
| Predicted risk | p | 15 |
| Member history | late-return rate | 10 |

### 5.4 Fuzzy priority levels (`services/fuzzy.py`)

- **Inputs and membership functions** (triangular/trapezoidal):
  - *lateness* (early, due soon, slightly, moderately, severely overdue)
  - *demand* (low, medium, high)
  - *fine* (small, moderate, large)
  - *risk* (low, medium, high)
- **Rules:** 10 Mamdani-style rules, for example "moderately overdue AND high demand → Critical" and "due soon AND high risk → Medium". AND = min, OR = max, and aggregation takes the max per level.
- **Output:** the level with the strongest support wins. The crisp value is the weighted centroid of the singletons Low 15, Medium 40, High 65, Critical 90.
- **Policy floors:** a recall is at least High, and a reservation-ready notice is at least Medium.
- **Fine summaries** have no deadline, so lateness is "not applicable" (all memberships 0).

### 5.5 Heap priority queue and anti-spam (`priority.py`, `notifier.py`)

- **Queue order:** Python `heapq` min-heap with key `(−level_rank, −score, arrival)`. Every Critical notice is served before any High notice, the utility score breaks ties within a level, and arrival order breaks exact ties.
- **Guard checks**, applied as items are popped:
  1. Duplicate in the same cycle → suppressed.
  2. Same dedupe key sent within the kind's cooldown → suppressed, *unless the fuzzy level escalated*.
  3. Member's daily limit reached → suppressed, unless the notice is Critical.
  4. Cycle capacity reached → the notice stays queued for the next cycle.
- **Channel:** Critical → SMS (or email if the member prefers in-app); High → the member's preference; Medium/Low → in-app.

### 5.6 Machine learning (`services/ml.py`)

- **Data.** 4,000 synthetic checkout records (seed 42) are generated from a hidden behavioural model: a per-member "habit" plus exam months, weekend checkout, unpaid fines, active loans, demand, category and member type. The library's own completed loans are appended; their features were frozen at checkout.
- **Features (checkout-time only):** prior loans, prior late rate, unpaid fines, active loans, title demand, loan days, exam period, weekend checkout, member type, category.
- **Excluded for leakage:** return date, renewals, the loan's own fine, notifications.
- **Excluded as sensitive:** name, gender, age, religion/caste, address, nationality, disability, contact details.
- **Models.** Logistic Regression (scaled numerics + one-hot) and a Decision Tree (depth 5, min leaf 25), both with class-balanced weights. A stratified 75/25 split is used, and the best test F1 is selected.
- **Explanations.**
  - Logistic Regression: per-feature contribution = coefficient × standardised value.
  - Decision Tree: the decision path, showing the share of late loans after each split.

## 6. Results

### 6.1 Tests

| Suite | Tests | Result |
|---|---|---|
| Backend — pytest | 74 | all passed |
| Frontend — Vitest | 21 | all passed |
| Production build (`tsc` + Vite) | — | success |
| Browser walkthrough (Playwright) | 3 roles, about 40 screens, light/dark, 360/768/820/1440 px | no console errors, no 5xx, no horizontal overflow |

The backend tests also cover concurrency. When two threads issue the same copy at once, exactly one succeeds. When a return races two reservations, exactly one hold is created.

### 6.2 Model comparison (seeded run, held-out 25%)

| Model | Accuracy | Precision | Recall | F1 | ROC AUC |
|---|---|---|---|---|---|
| **Logistic Regression** (selected) | 0.667 | 0.533 | 0.616 | **0.572** | 0.726 |
| Decision Tree | 0.652 | 0.518 | 0.513 | 0.516 | 0.663 |

Moderate accuracy is expected and intended: the hidden "habit" variable is not observable at checkout, as in real life. The model
is useful for ranking and gentle early reminders, not for deciding anything punitive. Prior late rate, unpaid fines and exam period
are the strongest factors.

### 6.3 Guided scenario outcome

The scenario starts on 2 Nov with a reserved book due on 4 Nov:

- **3 Nov:** a Medium due-soon reminder goes out in-app.
- **4 Nov:** a duplicate due-soon notice is suppressed by the cooldown.
- **5 Nov:** the book is overdue and reserved. `HIGH_RECALL_PRIORITY` fires and a **High** recall goes out by SMS.
- Two more members join the queue. Over the next six days, cooldown repeats are suppressed. On 11 Nov (7 days overdue), fuzzy rule F2 (moderately overdue ∧ high demand) raises the recall to **Critical**, overriding the cooldown, and R14 recommends a librarian call.
- **Return:** the fine is ₹6 (Sunday 8 Nov and the 9 Nov holiday were excluded). The copy is put on hold for the faculty member automatically, and she is notified.
- **Settlement:** a partial payment changes the fine status to *partially paid*, and the reservation is fulfilled when she collects the book.

### 6.4 Seeded environment

- 112 titles, 247 copies and 36 members.
- About 630 loans over 200 days, about 130 fines, and around 440 notifications.
- 21 agent cycles from the warm-up period.
- Pending lost-book approvals and severely overdue loans, so every chart and scenario has data from the start.

## 7. Limitations

- Email and SMS are simulated; there are no real gateways.
- The ML training data is synthetic, so the reported metrics validate the pipeline, not real-world accuracy.
- Fuzzy membership functions and utility weights are hand-designed (although the weights can be edited) rather than tuned from feedback.
- Auto mode runs from the browser tab, not as a server daemon.
- SQLite serialises writes. It is fine for one library desk, but not designed for heavy concurrent use.
- Notification outcomes are attributed to the most recent notices for the loan; this is not a causal estimate.

## 8. Future scope

- Real email/SMS/WhatsApp integration and two-way replies ("I'll return it tomorrow").
- Learn utility weights and fuzzy parameters from notification outcomes (reinforcement learning or bandits).
- Calibrated probabilities, with fairness metrics tracked over time and drift alerts.
- Demand forecasting to suggest buying extra copies of chronically reserved titles.
- Barcode or RFID scanning at the desk, and a mobile app for members.
- Move to PostgreSQL with a background scheduler for multi-branch libraries.
