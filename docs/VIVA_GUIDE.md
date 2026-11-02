# Viva Guide

## Before the viva (2 minutes)

1. `python run.py --reset`, then open http://localhost:8000. This gives a clean state with the clock on **2 Nov 2026**.
2. Open two browser windows: one signed in as **librarian@library.local / Librarian@123**, and a private window signed in as **member@library.local / Member@123** (Aarav).
3. Optional: switch one window to dark mode with the moon icon to show theming.

---

## 5-minute demo script

| Time | Where | What to show and say |
|---|---|---|
| 0:00 | **About the agent** | "This is an intelligent agent, not a CRUD app." Point to the PEAS cards and the environment table: partially observable, stochastic, sequential, dynamic, discrete. |
| 0:40 | **Dashboard** | KPIs, the overdue trend and notifications by priority. "Everything here comes from 21 days of the real agent loop run during seeding." |
| 1:00 | **Agent control → Play full demo** | Let it run. As steps appear, narrate: due-soon reminder (Medium, in-app) → book becomes overdue and **reserved** → rule R04 fires `HIGH_RECALL_PRIORITY` → **High recall by SMS** → a duplicate is **suppressed by the cooldown** → two more members queue up → fuzzy logic escalates to **Critical**, overriding the cooldown → return → the **fine skips a Sunday and a holiday** → the copy is **auto-allocated** to Dr. Iyer → partial payment. |
| 2:30 | Click **Explain cycle #…** on step 3 | Filter by `HIGH_RECALL_PRIORITY`. Open the loan: show working-memory facts, then the rules fired in order with their iteration numbers. "That is forward chaining." |
| 3:00 | **Notifications → Delivered → Why?** on the Critical recall | Walk through the 5-6 sections: rules, the utility score table (Σ weight × factor), fuzzy memberships and fired fuzzy rules, channel reason, anti-spam checks, prediction factors. Then show the **Priority queue** tab: "this is the heap order." |
| 3:40 | **Fines → Statement** on Aarav's fine | The day-by-day table: grace, Sunday, holiday, slab rate, running total. "Deterministic; ML never touches it." Show the **calculator** with a long overdue to demonstrate slabs and the cap. |
| 4:10 | **ML insights** | LR vs DT metrics, confusion matrices, feature importance, the excluded sensitive and leakage features. "Advisory only." |
| 4:35 | **Knowledge base** | As admin, create a **Loan** rule *IF predicted_risk ≥ 0.8 THEN RECOMMEND_RESTRICTION*: it is rejected by the **fairness guard**. Show the **Approvals** page: humans decide high-impact actions. |
| 4:55 | Member window | Aarav's inbox shows the recall with a "Why" line, and the polite template. |

---

## AI techniques in plain English

**Intelligent agent / PEAS.** An agent senses its environment and acts on it to reach goals. PEAS lists *how we judge it*
(Performance), *where it lives* (Environment), *what it can do* (Actuators) and *what it can see* (Sensors). Our agent wakes up once
per simulated day, looks at every loan, thinks, and acts.

**Sense-think-act loop.** Perceive → reason → act → record, repeated. Every cycle is saved so we can replay what the agent saw and why it acted.

**Rule-based expert system with forward chaining.** Knowledge is written as IF-THEN rules (e.g. *IF overdue AND reserved THEN high
recall priority*). Forward chaining starts from known facts, fires every rule whose IF part is true, adds the new facts, and repeats
until nothing new can be concluded. *Salience* decides which rule goes first. *Refraction* stops the same rule from firing twice on the same item.

**Fuzzy logic.** Real situations aren't black and white: 6 days overdue is "a bit slightly overdue and a bit moderately overdue".
Membership functions give each word a degree from 0 to 1. Rules combine those degrees with min (AND) and max (OR), and the strongest
supported level (Low/Medium/High/Critical) wins.

**Utility function.** A single 0–100 number summarising how important a notice is: a weighted sum of six understandable factors.
Because it is a plain sum, the score can be explained line by line.

**Priority queue (heap).** A data structure that always hands out the most important item next in O(log n). The key is (level, score), so Critical always comes first.

**Constraint-based anti-spam.** Before sending, each notice must pass constraints: not a duplicate, not within its cooldown (unless it got more urgent), and under the member's daily limit.

**Machine learning (supervised classification).** Learn from past loans (features → late or not) to estimate the chance a new loan will be late.
- *Logistic Regression* is a weighted sum of the features passed through a sigmoid.
- A *Decision Tree* is a series of yes/no questions.
- We compare the two on held-out data using accuracy, precision, recall, F1, AUC and the confusion matrix.

**Data leakage.** Using information that isn't available at prediction time (like the actual return date) makes a model look great in testing and useless in reality. We only use checkout-time features.

**Fairness and human-in-the-loop.** The model never sees sensitive attributes. Its output is advice only, so it can make a reminder come earlier but can never fine or restrict anyone. A taint check on the rule graph enforces this. Waivers, restrictions and "lost" declarations always need a librarian.

---

## 20 likely viva questions

1. **Why is this an "agent" and not just a program?**
   It runs autonomously in a perceive-think-act loop and chooses actions to optimise performance measures (fewer overdues, faster turnover, low spam). It also adapts to the environment state each day, keeps a record of its reasoning, and has a learning component.

2. **Give the PEAS for your agent.**
   - *P:* overdue rate/duration, reserved-book turnover, correct fines, notice resolution rate, low spam, no prediction-based penalties.
   - *E:* books, copies, members, loans, reservations, fines, policies, librarians, the calendar.
   - *A:* notifications, fine updates, allocations, approval requests, recommendations, logs.
   - *S:* loan/reservation/fine records, member history, the ML risk estimate.

3. **Classify the environment.**
   Partially observable (member intentions are hidden), stochastic, sequential, dynamic, discrete and multi-agent (cooperative librarians). The policies are known and member behaviour is learnt.

4. **Forward vs backward chaining — why forward?**
   Forward chaining is data-driven: we start from today's facts and want *all* consequences (every loan might need an action). Backward chaining is goal-driven, proving one hypothesis, which would mean asking "does loan X need a recall?" for every goal separately.

5. **How does your engine avoid infinite loops?**
   Rules only *add* facts; a fact is asserted at most once per entity (refraction); and the loop stops at a fixpoint with no new activations. There is also an iteration cap of 25.

6. **What is conflict resolution here?**
   When several rules match, they are fired in order of *salience* (higher first, then by code). Conditions are re-checked just before firing, so a higher-salience rule (R04 recall) can block a lower one that needs `HIGH_RECALL_PRIORITY` to be false (R12 overdue notice).

7. **Why fuzzy logic instead of thresholds?**
   Thresholds create cliffs: 6 vs 7 days would flip the priority suddenly. Fuzzy sets give graded membership, so rules can be written in natural language ("moderately overdue and high demand") and the level changes smoothly and explainably.

8. **Explain defuzzification in your system.**
   Each output level is a singleton (Low 15, Medium 40, High 65, Critical 90). The crisp value is the weighted average of these values by rule strength (centroid of singletons). The level shown is the one with maximum aggregated strength.

9. **Why have both a utility score *and* a fuzzy level?**
   The fuzzy level answers "which urgency class?" in linguistic terms. The utility score gives a fine-grained, additive, fully explainable ranking inside a class. The heap uses (level, score).

10. **Why a heap?**
    Many candidates are produced each cycle and dispatch capacity is limited. A heap gives the next most important notice in O(log n) per operation and supports carry-over to the next cycle.

11. **How do you prevent notification spam?**
    A dedupe key per (notice type, loan/reservation/member). Repeats within a type-specific cooldown are suppressed unless the fuzzy level escalated. There is a per-member daily limit (Critical notices bypass it), and a duplicate check within the same cycle. Suppressed notices are stored with their reason.

12. **How is the fine calculated? Can ML change it?**
    Day by day: grace days are free, holidays and Sundays are skipped (and don't advance the slab), the slab rate depends on the chargeable-day index, and the total is capped. Lost books add the replacement cost and a fee. It is pure integer arithmetic on dates and policy, so ML has no input at all.

13. **How are partial payments and waivers handled?**
    Payments are validated against the balance (no overpayment), and the status becomes partially paid / paid. Waivers need a reason of at least 5 characters, are recorded with the approver, and are audited. Members can only *request* a waiver, and that request goes to the approvals queue.

14. **What is data leakage and how did you avoid it?**
    Leakage is training on information unavailable at prediction time. We freeze features at checkout and exclude the return date, renewals, the loan's own fine and notifications.

15. **Why compare Logistic Regression and Decision Tree?**
    Both are interpretable. LR gives global coefficients and per-prediction contributions; a DT gives a readable decision path. We compare them on F1 (positive class = late), because accuracy alone hides poor recall on the minority class.

16. **Your accuracy is only about 67%. Is that bad?**
    It is realistic: the key driver (a member's habit) is hidden at checkout. The model is used only to rank loans for *gentle early reminders*, where a false positive costs one polite message, so moderate accuracy is acceptable. That is exactly why it is never used for penalties.

17. **How do you ensure fairness?**
    - No sensitive attributes are collected or used.
    - Group metrics by member type are monitored.
    - Predictions are advisory only.
    - A taint analysis over the rule graph rejects any penalising rule that depends on the prediction, directly or through chaining.
    - Every high-impact action needs human approval.

18. **What happens when two librarians act on the same copy at the same time?**
    Every transaction begins with `BEGIN IMMEDIATE`, which serialises writes. Copy status is changed with a compare-and-set update. Partial unique indexes allow only one active loan per copy and one hold per copy. The loser gets HTTP 409, and this is tested with real threads.

19. **How does reservation allocation work?**
    The queue for each title is FIFO. On return (a reflex action) or when a copy is free (rule R32), the first waiting member gets the copy *on hold* until an expiry date, and is notified. If they don't collect it, rule R31 expires the hold and the copy passes to the next member.

20. **What would you improve next?**
    Learning the weights and fuzzy parameters from notification outcomes (bandits/RL), real messaging channels, demand forecasting for purchasing extra copies, calibration and drift monitoring for the model, and a server-side scheduler with PostgreSQL for multiple branches.

---

## Handy numbers

- 19 default rules across 4 entity types; 10 fuzzy rules; 6 utility factors; 4 priority levels.
- Student policy: 4 books, 14 days, 2 renewals, 2-day grace, ₹2 → ₹5 → ₹10 per day, cap ₹300, lost after 30 days.
- Faculty policy: 10 books, 30 days, 3-day grace, ₹1 → ₹2 → ₹5 per day, cap ₹200.
- Tests: 74 backend + 21 frontend, all passing.
