import { ArrowDown, ArrowRight, Eye, Gauge, Hand, Brain, Globe } from "lucide-react";
import { Card, PageHeader, TableWrap } from "../components/ui";

const PEAS = [
  {
    key: "P", title: "Performance measures", icon: Gauge,
    items: ["Fewer overdue loans and shorter overdue duration", "Faster turnover of reserved (in-demand) books", "Fines that are 100% correct, explainable and consistent",
      "High notification resolution rate (member acts after a notice)", "Low notification spam: cooldowns, duplicates and daily limits respected",
      "Zero penalties based purely on predictions; every high-impact action human-approved"],
  },
  {
    key: "E", title: "Environment", icon: Globe,
    items: ["The library: titles, physical copies and their statuses", "Members (students, faculty, staff) and their history", "Loans, due dates, renewals and returns",
      "Reservation queues and holds", "Fines, payments, waivers, holidays and policies", "Librarians who approve or reject recommendations; the simulated calendar"],
  },
  {
    key: "A", title: "Actuators", icon: Hand,
    items: ["Create and dispatch notifications (in-app / simulated email / simulated SMS)", "Calculate and update fines (deterministic engine)",
      "Allocate returned copies to the reservation queue; expire uncollected holds", "Raise approval requests (mark lost, restrict, goodwill waiver)",
      "Recommend personal librarian follow-ups", "Write the decision timeline and audit trail"],
  },
  {
    key: "S", title: "Sensors", icon: Eye,
    items: ["Active loans: days overdue, days until due, renewals left", "Reservation demand per title and queue positions", "Returns, pickups and payments as they happen",
      "Member history: past loans and late-return rate", "Unpaid fines per member", "Late-return probability from the ML model (advisory input)"],
  },
];

const ENV = [
  ["Partially observable", "The agent cannot see whether a member still has the book, intends to return it, or has lost it — it only observes recorded events. The ML model estimates the hidden intention (risk)."],
  ["Stochastic", "Member behaviour is uncertain: the same situation (e.g. 3 days overdue) may or may not lead to a return tomorrow. Outcomes of a notification are not guaranteed."],
  ["Sequential", "Today's decisions affect tomorrow: a recall sent now creates a cooldown, a fine accrues day by day, a hold allocation changes who is next in the queue."],
  ["Dynamic", "The environment changes while the agent deliberates — members return, reserve and pay at any time (the simulation's background activity and librarian actions)."],
  ["Discrete", "Time advances in whole days; states (copy status, loan status, queue position) and actions (send, allocate, recommend) are discrete. Fuzzy logic adds graded truth on top."],
  ["Multi-agent (cooperative)", "Librarians and members act in the same environment; librarians share the goal and act as the human-in-the-loop approver for high-impact actions."],
  ["Known (rules) / partly unknown (behaviour)", "Library policies are fully known and encoded; member behaviour is learnt from (synthetic) data."],
];

const MAP = [
  ["Sense-think-act loop on a simulated clock", "Intelligent agent architecture (PEAS)", "Agent control center · Explainability → Agent cycle"],
  ["Editable IF-THEN rules, chaining to a fixpoint, salience & refraction", "Rule-based expert system · forward chaining · conflict resolution", "Knowledge base · cycle traces"],
  ["Membership functions, min/max rules, centroid defuzzification", "Fuzzy logic (Mamdani-style inference)", "Explainability → Fuzzy playground"],
  ["0-100 priority = Σ weight × normalised factor", "Utility-based agent · multi-attribute utility theory", "Notification explanations · Admin → weights"],
  ["Min-heap keyed on (−level, −score, arrival)", "Priority queue / heap data structure (search & scheduling)", "Notifications → Priority queue"],
  ["Cooldowns, duplicate suppression, daily limits", "Constraint satisfaction on actions", "Notifications → Suppressed"],
  ["Logistic Regression vs Decision Tree on checkout-time features", "Supervised learning · model evaluation · interpretability", "ML insights · loan details"],
  ["Taint analysis blocks prediction-based penalties; approvals queue", "Responsible AI · fairness · human-in-the-loop", "Knowledge base → Fairness guard · Approvals"],
  ["Slab/grace/holiday/cap fine engine", "Deterministic, auditable decision procedure (no ML)", "Fines → Statement & calculator"],
  ["FIFO reservation queue with automatic allocation", "Reactive (reflex) behaviour inside a deliberative agent", "Circulation → Return · Reservations"],
];

const LOOP = [
  { t: "Perceive", d: "Build a fact frame per loan, member, reservation and fine — days overdue, demand, unpaid fines, history, predicted risk.", c: "text-teal" },
  { t: "Think", d: "Forward-chain the knowledge base → conclusions. Score each notification candidate (utility) and classify it (fuzzy).", c: "text-[color:var(--series-1)]" },
  { t: "Act", d: "Persist fines, allocate/expire holds, serve the heap queue through anti-spam checks, request approvals, recommend follow-ups.", c: "text-accent" },
  { t: "Learn & explain", d: "Store percepts, firings, decisions and explanations; retrain the risk model on new history when asked.", c: "text-good" },
];

export default function About() {
  return (
    <div>
      <PageHeader eyebrow="Design" title="About the agent"
        description="Circulus is an intelligent agent for library circulation. This page maps every feature to the AI concept it demonstrates." />
      <div className="space-y-6">
        <section aria-labelledby="peas">
          <h2 id="peas" className="mb-3 text-2xl font-semibold">PEAS description</h2>
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
            {PEAS.map((p) => (
              <div key={p.key} className="card catalog-card px-4 pb-8 pt-4">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-ink font-display text-xl font-semibold text-paper">{p.key}</span>
                  <div><p className="font-display text-lg font-semibold leading-tight">{p.title}</p></div>
                  <p.icon className="ml-auto h-5 w-5 text-muted" aria-hidden />
                </div>
                <ul className="mt-3 space-y-1.5 text-sm text-ink2">{p.items.map((i) => <li key={i} className="flex gap-2"><span className="text-accent" aria-hidden>•</span>{i}</li>)}</ul>
              </div>
            ))}
          </div>
        </section>

        <Card title="The sense → think → act loop" subtitle="One cycle per simulated day (or on demand)">
          <ol className="grid gap-3 lg:grid-cols-4">
            {LOOP.map((s, i) => (
              <li key={s.t} className="relative rounded-lg border border-line p-4">
                <p className={`font-display text-xl font-semibold ${s.c}`}>{i + 1}. {s.t}</p>
                <p className="mt-1 text-sm text-ink2">{s.d}</p>
                {i < LOOP.length - 1 && <ArrowRight className="absolute -right-3 top-1/2 hidden h-5 w-5 -translate-y-1/2 rounded-full bg-surface text-muted lg:block" aria-hidden />}
                {i < LOOP.length - 1 && <ArrowDown className="mx-auto mt-2 h-4 w-4 text-muted lg:hidden" aria-hidden />}
              </li>
            ))}
          </ol>
          <p className="mt-3 text-sm text-ink2"><Brain className="mr-1.5 inline h-4 w-4 align-[-3px] text-accent" aria-hidden />Agent type: a <strong>utility-based, rule-driven agent with learning</strong> — rules decide <em>what</em> to do, utility + fuzzy logic decide <em>how urgently</em>, and a learnt model supplies an advisory belief about hidden member intentions.</p>
        </Card>

        <Card title="Task-environment classification">
          <TableWrap label="Environment properties">
            <table className="table-base">
              <thead><tr><th>Property</th><th>Justification</th></tr></thead>
              <tbody>{ENV.map(([k, v]) => <tr key={k}><td className="whitespace-nowrap font-medium">{k}</td><td className="text-ink2">{v}</td></tr>)}</tbody>
            </table>
          </TableWrap>
        </Card>

        <Card title="Feature → AI concept map">
          <TableWrap label="Feature map">
            <table className="table-base">
              <thead><tr><th>Feature</th><th>AI concept</th><th>Where to see it</th></tr></thead>
              <tbody>{MAP.map(([f, c, w]) => <tr key={f}><td>{f}</td><td className="font-medium">{c}</td><td className="text-ink2">{w}</td></tr>)}</tbody>
            </table>
          </TableWrap>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Ethics & human oversight">
            <ul className="space-y-2 text-sm text-ink2">
              <li>• No sensitive personal attributes (gender, age, religion, caste, address…) are stored or used as model features.</li>
              <li>• Fines are computed only from policy and dates; the ML model can never change an amount owed.</li>
              <li>• Predictions only adjust reminder timing/priority. A rule-graph taint analysis rejects any rule that would penalise based on a prediction.</li>
              <li>• Waivers, restrictions and lost-book declarations always require a librarian decision with a recorded reason.</li>
              <li>• Every action is logged with the simulated date, the actor and the reasoning.</li>
            </ul>
          </Card>
          <Card title="Algorithms at a glance">
            <ul className="space-y-2 text-sm text-ink2">
              <li><strong className="text-ink">Forward chaining</strong> — repeat: build conflict set, order by salience, fire, add facts; stop at fixpoint. O(iterations × rules × entities).</li>
              <li><strong className="text-ink">Fuzzy inference</strong> — trapezoid/triangle memberships; AND = min, OR = max; max-aggregation; centroid of singletons.</li>
              <li><strong className="text-ink">Utility score</strong> — weighted sum of six normalised factors, weights rescaled to 100.</li>
              <li><strong className="text-ink">Heap queue</strong> — Python <code className="font-mono text-xs">heapq</code>; push/pop O(log n).</li>
              <li><strong className="text-ink">ML</strong> — scikit-learn pipelines (scaling + one-hot), stratified 75/25 split, best F1 selected.</li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
