# Circulus — Intelligent Library Circulation, Fine Calculation and Priority Notification Agent

A full-stack **AI agent** for a college library, built as a Fundamentals of AI microproject. On every simulated day the agent
**perceives** circulation (loans, due dates, returns, reservations, demand, member history, unpaid fines) and **thinks** with a
forward-chaining expert system, fuzzy logic and a weighted utility function. It then **acts**: it calculates fines, prioritises and
sends notifications through a heap-based queue, allocates reserved books and recommends actions to librarians. Every decision is
stored and explained in the UI.

Everything runs **locally**. There are no paid APIs and no external services (SQLite, FastAPI, React, scikit-learn).

---

## Quick start

Requirements: **Python 3.10+** and **Node.js 18+** (npm).

```bash
python run.py
```

Then open **http://localhost:8000**. On first run this creates `backend/.venv`, installs dependencies, builds the frontend, seeds
the database (about 10 s) and starts the server. Later runs start in a few seconds.

| Command | What it does |
|---|---|
| `python run.py` | Install (first time), build, seed (first time) and serve on :8000 |
| `python run.py --reset` | Wipe and re-seed the database, then serve |
| `python run.py --test` | Run backend (pytest) and frontend (Vitest) tests |
| `python run.py --dev` | Hot-reload mode: API on :8000 and Vite dev server on :5173 |

<details>
<summary>Manual steps (if you prefer)</summary>

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip install -r requirements.txt
.venv/bin/python -m app.seed --reset
cd ../frontend && npm install && npm run build
cd ../backend && .venv/bin/python -m uvicorn app.main:app --port 8000
```
</details>

## Demo logins (also shown on the login page)

| Role | Email | Password | Can do |
|---|---|---|---|
| Admin | `admin@library.local` | `Admin@123` | Users, policies, holidays, agent settings, KB editing, ML retraining, all analytics |
| Librarian | `librarian@library.local` | `Librarian@123` | Books, circulation, fines, approvals, notifications, agent control |
| Member | `member@library.local` | `Member@123` | Search, own loans/renewals, reservations, fines, notifications (student Aarav Sharma) |

All 35 other seeded members can also sign in, each with their college email (e.g. `meera.iyer@college.edu`) and `Member@123`. The login page has a searchable list of these accounts; click one to fill the form.

- **Create account** (tab on the login page): anyone can register as a library **member** (student, faculty or staff) with their own email and password. Staff accounts can only be created by an admin, in Administration → Users.
- **Change password**: available from the sidebar for every account. Members added by a librarian start with `Member@123` and should change it.

## Feature overview

**Library operations**
- Catalogue of 112 real titles with 247 barcoded physical copies (available / on loan / on hold / lost / maintenance), with search, filters and sorting.
- 36 members (students, faculty, staff) and role-based accounts with PBKDF2-hashed passwords and signed tokens.
- Issue, return, renew and reserve, with a FIFO reservation queue. A returned copy is allocated to the next member automatically, and holds that aren't collected expire.
- Configurable borrowing limits, loan periods, renewal limits, hold windows and fine slabs per member type.
- Full circulation history, approvals queue and audit log.

**The intelligent agent**
- **PEAS model and environment classification** on the *About the agent* page.
- **Sense-think-act loop**: every cycle stores its percepts, rule firings, decisions, actions and explanations.
- **Forward-chaining expert system**: 19 editable rules with salience, refraction and chaining to a fixpoint, plus a rule sandbox.
- **Deterministic fine engine**: slab rates, grace period, holidays and Sundays excluded, caps, lost-book charges, partial payments, and waivers that require a reason. Every fine has a day-by-day statement.
- **Priority notifications**: a 0-100 weighted utility score, fuzzy levels (Critical/High/Medium/Low) and a heap priority queue. Cooldowns, duplicate suppression and daily limits prevent spam. The channel (in-app, or simulated email/SMS) depends on priority and member preference, and every notice carries a "why was this sent" explanation.
- **Machine learning**: a reproducible synthetic dataset (clearly labelled), with Logistic Regression and Decision Tree compared on accuracy, precision, recall, F1, AUC, confusion matrix and feature importance. Each prediction shows its own factors, and there is a retrain button with model selection.
- **Fairness and oversight**: no sensitive attributes are used. Predictions are advisory only, and a taint analysis rejects any rule that would penalise based on a prediction. Waivers, restrictions and lost-book declarations need librarian approval.

**Simulation for the viva**
- A simulated clock: +1 day, +7 days, reset, run one cycle, or auto mode. Optional background member activity.
- A **one-click guided demo**: a reserved book goes overdue → priority rises → recall sent (with a duplicate suppressed) → Critical escalation → fine with a holiday excluded → return → automatic allocation → partial payment. Each step's reasoning appears on a live timeline.

## Pages

Dashboard (staff and member versions) · Catalog · Members · Circulation / My loans · Reservations · Fines (with fine calculator) ·
Approvals · Notification center (heap queue view) · Agent control center · Explainability (cycle traces, live loan reasoning,
notification reasoning, fuzzy playground) · Knowledge base editor · ML insights · Analytics · About the agent · Administration · Audit log.

Light and dark themes, responsive down to 360 px, keyboard navigable, with labelled forms, live regions and table views for every chart.

## Architecture

```mermaid
flowchart LR
  subgraph Browser["React + TypeScript (Vite, Tailwind, Recharts)"]
    UI[Role-based pages] --> API[(Typed API client)]
  end
  API -- JSON / Bearer token --> R

  subgraph Server["FastAPI (Python)"]
    R[Routers + role guards + Pydantic validation] --> S
    subgraph S[Services]
      AG[Agent loop<br/>perceive · think · act]
      INF[Forward-chaining<br/>inference engine]
      KB[Knowledge base<br/>+ fairness taint check]
      FZ[Fuzzy classifier]
      PR[Utility score +<br/>heap priority queue]
      NT[Notifier<br/>anti-spam + channels]
      FE[Deterministic<br/>fine engine]
      CI[Circulation<br/>issue/return/reserve]
      ML[scikit-learn<br/>risk models]
      OV[Approvals<br/>human oversight]
      SIM[Simulated clock<br/>+ guided demo]
    end
    AG --> INF --> KB
    AG --> PR --> FZ
    AG --> NT
    AG --> FE
    AG --> OV
    CI --> FE
    CI --> ML
    SIM --> AG
  end
  S --> DB[(SQLite<br/>BEGIN IMMEDIATE + partial unique indexes)]
  ML --> MF[(joblib model files)]
```

**Agent cycle (one simulated day)**

```mermaid
sequenceDiagram
  participant C as Clock
  participant P as Perceive
  participant T as Think
  participant A as Act
  participant H as Librarian
  C->>P: new day
  P->>P: fact frames per loan / member / reservation / fine
  P->>T: working memory
  T->>T: forward chaining to fixpoint (salience, refraction)
  T->>T: utility score + fuzzy level per notification candidate
  T->>A: conclusions + priorities
  A->>A: update fines · expire/allocate holds · heap queue → anti-spam → dispatch
  A->>H: approval requests (mark lost / restrict / waiver)
  A->>A: store cycle, events, explanations
```

### Project layout

```
backend/
  app/
    main.py            FastAPI app (also serves the built frontend)
    models.py          SQLAlchemy models (users, members, books, copies, loans, reservations, fines, payments,
                       waivers, holidays, approvals, notifications, rules, settings, agent_cycles, agent_events,
                       ml_models, audit_logs)
    services/          agent, inference, knowledge_base, fuzzy, priority, notifier, fines, circulation,
                       oversight, ml, simulation, demo, settings, audit
    routers/           REST endpoints per area
    seed.py            deterministic demo data + 21-day warm-up through the real agent loop
  tests/               pytest suite (74 tests)
frontend/
  src/lib/             API client, types, scoring mirror, roles, validation, formatting
  src/components/      UI kit, charts, explanation views, layout
  src/pages/           one file per page
  src/test/            Vitest suite (21 tests)
docs/                  PROJECT_REPORT.md, VIVA_GUIDE.md
run.py                 one-command launcher
```

## Testing

```bash
python run.py --test
```

- **Backend (pytest, 74 tests):** fine engine (grace, slabs, holidays, Sundays, caps, lost books, partial payments, waivers); forward chaining (chaining order, negation, refraction, rule comparisons, disabled rules, proof chains); KB validation and the fairness guard; utility scoring, fuzzy memberships and levels, heap ordering and channels; cooldowns, escalation override, duplicate suppression and daily limits; reservation allocation (FIFO, holds, cancellation hand-off); concurrent issue and return-vs-reserve races; role-based permissions; agent cycles, approvals, ML, and the **full guided demo scenario**.
- **Frontend (Vitest, 21 tests):** scoring parity with the backend, fuzzy functions, queue ordering, role routing, form validation, formatting, API error handling and accessible components.

## Known limitations

- Email and SMS are **simulated**: they are stored and shown in the UI, never sent.
- The ML dataset is **synthetic**, so the metrics show the method, not real-world accuracy.
- Auto mode is driven by the open browser tab. It pauses if you close the app.
- SQLite with serialised write transactions is ideal for a single-machine demo, not for many concurrent users.
- **Reset simulation** re-runs the seeder, so any data you created is discarded.
