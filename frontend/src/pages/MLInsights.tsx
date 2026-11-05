import { useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BrainCircuit, CheckCircle2, FlaskConical, RefreshCw, ShieldCheck } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useApi } from "../lib/useApi";
import { post } from "../lib/api";
import { ALGO_LABELS, fmtDate, humanise, pct } from "../lib/format";
import type { Factor, MLModel, Prediction } from "../lib/types";
import { can } from "../lib/roles";
import { Async, Card, Field, Notice, PageHeader, RiskPill, StatusBadge, TableWrap, cx } from "../components/ui";
import { axisProps, ChartCard, ChartTooltip, gridProps, SERIES } from "../components/charts";
import { PredictionFactors } from "../components/explain";
import { useAction } from "../components/toast";

interface Summary {
  latest: MLModel[]; history: MLModel[]; selected: MLModel | null;
  features: { name: string; description: string; type: string }[]; excluded_leakage: string[]; excluded_sensitive: string[]; categories: string[];
  sample_rows: Record<string, unknown>[];
  top_risk_loans: { loan_id: number; title: string; member_name: string; risk_score: number; risk_label: string; factors: Factor[]; algo: string }[];
}

const METRICS = ["accuracy", "precision", "recall", "f1", "roc_auc"] as const;

export default function MLInsights() {
  const user = useUser();
  const state = useApi<Summary>("/api/ml/summary");
  const act = useAction();
  const [training, setTraining] = useState(false);
  const [form, setForm] = useState({ n_samples: "4000", seed: "42", include_history: true });

  async function retrain(e: FormEvent) {
    e.preventDefault();
    const n = Number(form.n_samples), s = Number(form.seed);
    if (!(n >= 500 && n <= 20000) || !(s >= 0 && s <= 10000)) return;
    setTraining(true);
    const r = await act(() => post("/api/ml/retrain", { n_samples: n, seed: s, include_history: form.include_history }), "Both models retrained — best F1 selected automatically");
    setTraining(false);
    if (r) state.reload();
  }
  async function select(id: number) {
    const r = await act(() => post(`/api/ml/models/${id}/select`), "Model selected for new checkouts");
    if (r) state.reload();
  }

  return (
    <div>
      <PageHeader eyebrow="Supervised learning" title="ML insights"
        description="Logistic Regression vs Decision Tree predicting late returns from checkout-time features. Predictions are decision support only: they never set fines or trigger penalties." />
      <Async state={state}>
        {(d) => {
          const models = d.latest;
          const comparison = METRICS.map((m) => ({ metric: m === "roc_auc" ? "ROC AUC" : humanise(m), ...Object.fromEntries(models.map((x) => [x.algo, x.metrics[m]])) }));
          return (
            <div className="space-y-6">
              <Notice tone="info"><strong>Synthetic data.</strong> {d.latest[0]?.dataset_info.label}: {d.latest[0]?.dataset_info.synthetic_rows} generated rows (seed {d.latest[0]?.dataset_info.seed}) + {d.latest[0]?.dataset_info.history_rows} completed library loans. Train {d.latest[0]?.dataset_info.train_rows} / test {d.latest[0]?.dataset_info.test_rows}, {pct(d.latest[0]?.dataset_info.positive_rate)} late.</Notice>
              <div className="grid gap-4 lg:grid-cols-2">
                {models.map((m) => (
                  <Card key={m.id} title={<span className="flex items-center gap-2"><BrainCircuit className="h-4 w-4 text-accent" aria-hidden />{ALGO_LABELS[m.algo]}</span>}
                    subtitle={`v${m.version} · trained ${fmtDate(m.trained_at)}`}
                    actions={m.is_selected ? <StatusBadge status="active" label="in use" /> : can.retrainModel(user.role) && <button className="btn-secondary px-2.5 py-1 text-xs" onClick={() => select(m.id)}>Use this model</button>}>
                    <div className="grid grid-cols-5 gap-2 text-center">
                      {METRICS.map((k) => <div key={k}><p className="text-[10px] uppercase tracking-wider text-muted">{k === "roc_auc" ? "AUC" : k}</p><p className="num font-display text-xl font-semibold">{m.metrics[k].toFixed(2)}</p></div>)}
                    </div>
                    <div className="mt-4 grid gap-4 sm:grid-cols-[auto,1fr]">
                      <Confusion cm={m.metrics.confusion_matrix} />
                      <div className="min-w-0">
                        <p className="eyebrow mb-1">Feature importance {m.algo === "logistic_regression" ? "(|coefficient| share)" : "(Gini importance)"}</p>
                        <ul className="space-y-1">
                          {m.feature_importance.slice(0, 7).map((f, i) => (
                            <li key={f.feature} className="text-xs">
                              <div className="flex justify-between gap-2"><span className="truncate">{f.feature}</span><span className="num font-mono">{pct(f.importance, 1)}{f.direction.startsWith("raises") ? " ▲" : f.direction.startsWith("lowers") ? " ▼" : ""}</span></div>
                              <div className="h-1.5 rounded-full bg-sunken"><div className="h-1.5 rounded-full" style={{ width: `${Math.min(f.importance / (m.feature_importance[0]?.importance || 1), 1) * 100}%`, background: SERIES[i === 0 ? 0 : 0] }} /></div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>

              <ChartCard title="Model comparison" subtitle="Held-out test set (25%, stratified)" rows={comparison as Record<string, unknown>[]}
                legend={models.map((m, i) => ({ label: ALGO_LABELS[m.algo], color: SERIES[i] }))}
                columns={[{ key: "metric", label: "Metric" }, ...models.map((m) => ({ key: m.algo, label: ALGO_LABELS[m.algo], format: (v: unknown) => (v as number).toFixed(3) }))]}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={comparison} margin={{ top: 8, right: 8, bottom: 0, left: -18 }} barGap={2} barCategoryGap="30%">
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="metric" {...axisProps} />
                    <YAxis domain={[0, 1]} {...axisProps} axisLine={false} />
                    <Tooltip content={<ChartTooltip format={(v) => v.toFixed(3)} />} cursor={{ fill: "rgb(var(--sunken))" }} />
                    {models.map((m, i) => <Bar key={m.algo} dataKey={m.algo} name={ALGO_LABELS[m.algo]} fill={SERIES[i]} maxBarSize={24} radius={[4, 4, 0, 0]} />)}
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <div className="grid gap-6 xl:grid-cols-2">
                <Card title={<span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-teal" aria-hidden />Fairness & data hygiene</span>}>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div><p className="eyebrow mb-1">Never collected or used</p><ul className="space-y-0.5 text-sm">{d.excluded_sensitive.map((x) => <li key={x}>✕ {x}</li>)}</ul></div>
                    <div><p className="eyebrow mb-1">Excluded to prevent leakage</p><ul className="space-y-0.5 text-sm">{d.excluded_leakage.map((x) => <li key={x}>✕ {x}</li>)}</ul></div>
                  </div>
                  {d.selected && (
                    <>
                      <p className="eyebrow mb-1 mt-4">Selected model by member type (test set)</p>
                      <TableWrap label="Group metrics"><table className="table-base num"><thead><tr><th>Group</th><th>n</th><th>Actual late</th><th>Flagged high</th><th>Recall</th></tr></thead>
                        <tbody>{Object.entries(d.selected.metrics.by_member_type).map(([g, v]) => <tr key={g}><td>{humanise(g)}</td><td>{v.n}</td><td>{pct(v.actual_late_rate)}</td><td>{pct(v.predicted_high_rate)}</td><td>{pct(v.recall)}</td></tr>)}</tbody></table></TableWrap>
                      <p className="mt-2 text-xs text-muted">Member type is an academic role that sets loan rules, not a protected attribute. Group rates are monitored so a librarian can spot disparities.</p>
                    </>
                  )}
                </Card>
                <Card title="Checkout-time features">
                  <ul className="space-y-1.5 text-sm">{d.features.map((f) => <li key={f.name}><code className="font-mono text-xs">{f.name}</code> <span className="text-xs text-muted">({f.type})</span><span className="block text-ink2">{f.description}</span></li>)}</ul>
                </Card>
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <WhatIf categories={d.categories} />
                <Card title="Highest-risk active loans" subtitle="With the main factors behind each prediction">
                  <ul className="space-y-3">
                    {d.top_risk_loans.map((l) => (
                      <li key={l.loan_id} className="rounded-lg border border-line p-3 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{l.title}</span><RiskPill score={l.risk_score} label={l.risk_label} /></div>
                        <p className="text-xs text-muted">{l.member_name} · loan #{l.loan_id} · {ALGO_LABELS[l.algo] ?? ""}</p>
                        <p className="mt-1 text-xs text-ink2">{l.factors.slice(0, 3).map((f) => f.text).join(" · ")}</p>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>

              <div className="grid gap-6 xl:grid-cols-[1fr,1.4fr]">
                {can.retrainModel(user.role) && (
                  <Card title={<span className="flex items-center gap-2"><RefreshCw className="h-4 w-4 text-accent" aria-hidden />Retrain</span>} subtitle="Regenerates the synthetic dataset, trains both models, saves them and selects the best F1">
                    <form onSubmit={retrain} className="grid gap-3 sm:grid-cols-2" noValidate>
                      <Field label="Synthetic rows" htmlFor="ml-n" error={!(+form.n_samples >= 500 && +form.n_samples <= 20000) ? "500–20,000" : null}><input id="ml-n" className="input" inputMode="numeric" value={form.n_samples} onChange={(e) => setForm({ ...form, n_samples: e.target.value })} /></Field>
                      <Field label="Random seed" htmlFor="ml-s" error={!(+form.seed >= 0 && +form.seed <= 10000) ? "0–10,000" : null}><input id="ml-s" className="input" inputMode="numeric" value={form.seed} onChange={(e) => setForm({ ...form, seed: e.target.value })} /></Field>
                      <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" className="h-4 w-4 accent-[rgb(var(--accent))]" checked={form.include_history} onChange={(e) => setForm({ ...form, include_history: e.target.checked })} />Include the library's completed loans</label>
                      <button className="btn-primary sm:col-span-2" disabled={training}>{training ? "Training…" : "Retrain both models"}</button>
                    </form>
                  </Card>
                )}
                <Card title="Synthetic data sample" subtitle="First rows of a generated dataset (seed 7)" className={cx(!can.retrainModel(user.role) && "xl:col-span-2")}>
                  <TableWrap label="Sample rows"><table className="table-base num text-xs">
                    <thead><tr>{Object.keys(d.sample_rows[0] ?? {}).filter((k) => k !== "synthetic").map((k) => <th key={k}>{k}</th>)}</tr></thead>
                    <tbody>{d.sample_rows.slice(0, 8).map((r, i) => <tr key={i}>{Object.entries(r).filter(([k]) => k !== "synthetic").map(([k, v]) => <td key={k} className="whitespace-nowrap font-mono">{String(v)}</td>)}</tr>)}</tbody></table></TableWrap>
                </Card>
              </div>

              <Card title="Training history">
                <TableWrap label="Model history"><table className="table-base num"><thead><tr><th>Version</th><th>Algorithm</th><th>Trained</th><th>Accuracy</th><th>F1</th><th>AUC</th><th>Status</th></tr></thead>
                  <tbody>{d.history.map((m) => <tr key={m.id}><td>v{m.version}</td><td>{ALGO_LABELS[m.algo]}</td><td>{fmtDate(m.trained_at)}</td><td>{m.metrics.accuracy.toFixed(3)}</td><td>{m.metrics.f1.toFixed(3)}</td><td>{m.metrics.roc_auc.toFixed(3)}</td>
                    <td>{m.is_selected ? <span className="inline-flex items-center gap-1 text-good"><CheckCircle2 className="h-3.5 w-3.5" aria-hidden />selected</span> : "—"}</td></tr>)}</tbody></table></TableWrap>
              </Card>
            </div>
          );
        }}
      </Async>
    </div>
  );
}

function Confusion({ cm }: { cm: { tn: number; fp: number; fn: number; tp: number } }) {
  const max = Math.max(cm.tn, cm.fp, cm.fn, cm.tp) || 1;
  const cell = (v: number, label: string, good: boolean) => (
    <div className="flex h-16 w-20 flex-col items-center justify-center rounded-md text-xs" style={{ background: `color-mix(in srgb, ${good ? "var(--series-1)" : "var(--series-2)"} ${Math.round(12 + (v / max) * 50)}%, transparent)` }}>
      <span className="num font-display text-lg font-semibold text-ink">{v}</span><span className="text-ink2">{label}</span>
    </div>
  );
  return (
    <div>
      <p className="eyebrow mb-1">Confusion matrix</p>
      <div className="grid grid-cols-[auto,auto,auto] items-center gap-1 text-[10px] text-muted">
        <span /><span className="text-center">pred. on time</span><span className="text-center">pred. late</span>
        <span className="pr-1 text-right">actual<br />on time</span>{cell(cm.tn, "TN", true)}{cell(cm.fp, "FP", false)}
        <span className="pr-1 text-right">actual<br />late</span>{cell(cm.fn, "FN", false)}{cell(cm.tp, "TP", true)}
      </div>
    </div>
  );
}

function WhatIf({ categories }: { categories: string[] }) {
  const [f, setF] = useState({ prior_loans: 8, prior_late_rate: 0.25, unpaid_fines: 0, active_loans: 1, title_demand: 0, loan_days: 14, exam_period: 0, weekend_checkout: 0, member_type: "student", category: categories[0] ?? "Computer Science" });
  const [res, setRes] = useState<Prediction | null>(null);
  const act = useAction();
  const num = (k: keyof typeof f, label: string, step = 1, max = 100) => (
    <Field label={label} htmlFor={`wi-${k}`}><input id={`wi-${k}`} type="number" min={0} max={max} step={step} className="input" value={f[k] as number} onChange={(e) => setF({ ...f, [k]: Number(e.target.value) })} /></Field>
  );
  async function run(e: FormEvent) {
    e.preventDefault();
    const r = await act(() => post<Prediction>("/api/ml/predict", f));
    if (r) setRes(r);
  }
  return (
    <Card title={<span className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-accent" aria-hidden />What-if prediction</span>} subtitle="Explore how checkout-time factors move the selected model">
      <form onSubmit={run} className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {num("prior_loans", "Prior loans", 1, 500)}
        {num("prior_late_rate", "Prior late rate", 0.05, 1)}
        {num("unpaid_fines", "Unpaid fines ₹", 10, 100000)}
        {num("active_loans", "Active loans", 1, 20)}
        {num("title_demand", "Waiting for title", 1, 20)}
        {num("loan_days", "Loan days", 1, 120)}
        <Field label="Member type" htmlFor="wi-mt"><select id="wi-mt" className="input" value={f.member_type} onChange={(e) => setF({ ...f, member_type: e.target.value })}><option value="student">Student</option><option value="faculty">Faculty</option><option value="staff">Staff</option></select></Field>
        <Field label="Category" htmlFor="wi-cat"><select id="wi-cat" className="input" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{categories.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <div className="flex flex-col justify-end gap-1 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" className="accent-[rgb(var(--accent))]" checked={!!f.exam_period} onChange={(e) => setF({ ...f, exam_period: e.target.checked ? 1 : 0 })} />Exam month</label>
          <label className="flex items-center gap-2"><input type="checkbox" className="accent-[rgb(var(--accent))]" checked={!!f.weekend_checkout} onChange={(e) => setF({ ...f, weekend_checkout: e.target.checked ? 1 : 0 })} />Weekend</label>
        </div>
        <button className="btn-primary col-span-2 sm:col-span-3">Predict</button>
      </form>
      {res && <div className="mt-4 border-t border-line pt-4"><PredictionFactors prediction={res} /></div>}
    </Card>
  );
}
