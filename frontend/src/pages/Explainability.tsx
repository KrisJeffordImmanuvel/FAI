import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { get, qs } from "../lib/api";
import { KIND_LABELS, fmtDate, humanise, rupees } from "../lib/format";
import type { Cycle, CycleDetail, FineBreakdown, Firing, FuzzyResult, Level, Loan, Notification, Page, Prediction, ScoreItem } from "../lib/types";
import { Async, Card, EmptyState, ErrorState, KeyValue, LevelBadge, Notice, PageHeader, Spinner, StatusBadge, Tabs, cx } from "../components/ui";
import { FineStatement, FuzzyView, NotificationExplanation, PredictionFactors, RuleTrace, ScoreBreakdown } from "../components/explain";
import { axisProps, ChartTooltip, gridProps, Legend, SERIES } from "../components/charts";

type Tab = "cycle" | "loan" | "fuzzy" | "notification";

export default function Explainability() {
  const [params, setParams] = useSearchParams();
  const initial = (params.get("cycle") ? "cycle" : params.get("loan") ? "loan" : params.get("notification") ? "notification" : "cycle") as Tab;
  const [tab, setTab] = useState<Tab>(initial);
  useEffect(() => {
    if (params.get("notification")) setTab("notification");
    else if (params.get("loan")) setTab("loan");
    else if (params.get("cycle")) setTab("cycle");
  }, [params]);
  return (
    <div>
      <PageHeader eyebrow="Glass box" title="Explainability"
        description="Inspect exactly why the agent acted: which rules fired on which facts, the fuzzy memberships, the utility-score breakdown and the factors behind each prediction." />
      <div className="mb-5"><Tabs label="Explanation type" value={tab} onChange={(t) => { setTab(t); setParams({}); }} options={[
        { value: "cycle", label: "Agent cycle" }, { value: "loan", label: "Loan (live)" }, { value: "notification", label: "Notification" }, { value: "fuzzy", label: "Fuzzy playground" }]} /></div>
      {tab === "cycle" && <CycleExplorer initialId={params.get("cycle") ? Number(params.get("cycle")) : null} />}
      {tab === "loan" && <LoanExplorer initialId={params.get("loan") ? Number(params.get("loan")) : null} />}
      {tab === "notification" && <NotificationExplorer initialId={params.get("notification") ? Number(params.get("notification")) : null} />}
      {tab === "fuzzy" && <FuzzyPlayground />}
    </div>
  );
}

function CycleExplorer({ initialId }: { initialId: number | null }) {
  const { tick } = useAgent();
  const cycles = useApi<Cycle[]>("/api/agent/cycles?limit=40", [tick]);
  const [id, setId] = useState<number | null>(initialId);
  useEffect(() => { if (initialId) setId(initialId); }, [initialId]);
  useEffect(() => { if (id === null && cycles.data?.length) setId(cycles.data[0].id); }, [cycles.data, id]);
  const detail = useApi<CycleDetail>(id ? `/api/agent/cycles/${id}` : null);
  const [fact, setFact] = useState("");
  const [entity, setEntity] = useState("");

  const decisions = useMemo(() => (detail.data?.decisions ?? []).filter((d) => d.entity && (!entity || d.entity === entity) && (!fact || d.asserted?.includes(fact))), [detail.data, fact, entity]);
  const allFacts = useMemo(() => [...new Set((detail.data?.firings ?? []).map((f) => f.asserted))].sort(), [detail.data]);
  const byEntity = useMemo(() => {
    const m = new Map<string, Firing[]>();
    for (const f of detail.data?.firings ?? []) {
      const k = `${f.entity}:${f.entity_id}`;
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(f);
    }
    return m;
  }, [detail.data]);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div className="grid gap-6 xl:grid-cols-[300px,1fr]">
      <Card title="Cycles" bodyClass="p-2">
        <Async state={cycles} isEmpty={(c) => c.length === 0} empty={<EmptyState title="No cycles yet" />}>
          {(list) => (
            <ul className="max-h-[70vh] space-y-1 overflow-y-auto">
              {list.map((c) => (
                <li key={c.id}><button onClick={() => setId(c.id)} aria-current={c.id === id}
                  className={cx("w-full rounded-lg px-3 py-2 text-left text-sm", c.id === id ? "bg-ink text-paper" : "hover:bg-sunken")}>
                  <span className="font-mono text-xs opacity-70">#{c.id} · {c.mode}</span><span className="block font-medium">{fmtDate(c.sim_date)}</span>
                  <span className="block text-xs opacity-70">{c.firing_count} firings · {c.percepts.overdue_loans ?? 0} overdue</span></button></li>
              ))}
            </ul>
          )}
        </Async>
      </Card>
      <div className="min-w-0 space-y-6">
        {!id ? <EmptyState title="Choose a cycle" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.reload} /> : !detail.data ? <Spinner /> : (
          <>
            <Card title={`Cycle #${detail.data.id} · ${fmtDate(detail.data.sim_date)}`} subtitle={`${detail.data.mode} · ${detail.data.duration_ms} ms`}>
              <p className="mb-3 text-sm">{detail.data.summary}</p>
              <p className="eyebrow mb-1">Percepts (sensors)</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                {Object.entries(detail.data.percepts).map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-line px-3 py-2"><p className="text-[11px] text-muted">{humanise(k)}</p><p className="num font-mono">{k.includes("fines") ? rupees(v) : v}</p></div>
                ))}
              </div>
            </Card>
            <Card title="Think: forward-chaining decisions" subtitle={`${detail.data.firings.length} rule firings across ${byEntity.size} entities`}
              actions={<div className="flex gap-2">
                <label><span className="sr-only">Entity</span><select className="input py-1 text-xs" value={entity} onChange={(e) => setEntity(e.target.value)}>
                  <option value="">All entities</option>{["loan", "member", "reservation", "fine"].map((e) => <option key={e} value={e}>{humanise(e)}</option>)}</select></label>
                <label><span className="sr-only">Asserted fact</span><select className="input py-1 text-xs" value={fact} onChange={(e) => setFact(e.target.value)}>
                  <option value="">Any asserted fact</option>{allFacts.map((f) => <option key={f}>{f}</option>)}</select></label>
              </div>}>
              {decisions.length === 0 ? <EmptyState title="No entity matches these filters" /> : (
                <ul className="space-y-2">
                  {decisions.slice(0, 80).map((d) => {
                    const key = `${d.entity}:${d.id}`;
                    return (
                      <li key={key} className="rounded-lg border border-line">
                        <button className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left text-sm hover:bg-sunken/60" onClick={() => setOpen(open === key ? null : key)} aria-expanded={open === key}>
                          <span className="min-w-0 flex-1 font-medium">{d.label}</span>
                          <span className="flex flex-wrap gap-1">{d.asserted?.map((a) => <code key={a} className={cx("rounded px-1.5 py-0.5 font-mono text-[10px]", a.startsWith("NOTIFY") || a.startsWith("RECOMMEND") || a.startsWith("ESCALATE") ? "bg-accent/10 text-accent" : "bg-sunken")}>{a}</code>)}</span>
                        </button>
                        {open === key && (
                          <div className="grid gap-4 border-t border-line p-3 lg:grid-cols-[260px,1fr]">
                            <div><p className="eyebrow mb-1">Working memory (facts)</p>
                              <KeyValue items={Object.entries(d.facts ?? {}).map(([k, v]) => [<span key={k} className="font-mono text-xs">{k}</span>, <span key={`${k}v`} className="font-mono text-xs">{String(v)}</span>])} /></div>
                            <div><p className="eyebrow mb-1">Rules fired, in order</p><RuleTrace firings={byEntity.get(key) ?? []} /></div>
                          </div>
                        )}
                      </li>
                    );
                  })}
                  {decisions.length > 80 && <li className="text-xs text-muted">Showing 80 of {decisions.length} — narrow with the filters.</li>}
                </ul>
              )}
            </Card>
            <Card title="Act: notifications produced in this cycle" subtitle="Including suppressed ones — open the Notification tab to see full reasoning">
              {detail.data.notifications.length === 0 ? <EmptyState title="No notifications in this cycle" /> : (
                <ul className="divide-y divide-line">
                  {detail.data.notifications.slice(0, 40).map((n) => (
                    <li key={n.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                      <LevelBadge level={n.level} score={n.score} /><StatusBadge status={n.status} /><span className="min-w-0 flex-1">{n.member_name}: {n.subject}</span>
                      <Link className="btn-ghost px-2 py-1 text-xs" to={`/explain?notification=${n.id}`}>Explain</Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

interface LoanExplain {
  loan_id: number; label: string; sim_date: string; facts: Record<string, unknown>; asserted: string[]; firings: Firing[]; notification_kind: string | null;
  priority: { score: number; level: Level; breakdown: ScoreItem[]; fuzzy: FuzzyResult }; fine: FineBreakdown; prediction: (Prediction & { features: Record<string, unknown> }) | null;
}

function LoanExplorer({ initialId }: { initialId: number | null }) {
  const { tick } = useAgent();
  const loans = useApi<Page<Loan>>(`/api/loans${qs({ status: "active", page_size: 200 })}`, [tick]);
  const [id, setId] = useState<number | null>(initialId);
  const [data, setData] = useState<LoanExplain | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!id && loans.data?.items.length) {
      const pick = loans.data.items.find((l) => (l.days_overdue ?? 0) > 0) ?? loans.data.items[0];
      setId(pick.id);
    }
  }, [loans.data, id]);
  useEffect(() => {
    if (!id) return;
    setData(null);
    get<LoanExplain>(`/api/explain/loan/${id}`).then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  }, [id, tick]);
  return (
    <div className="space-y-6">
      <Card title="Choose an active loan" subtitle="The agent re-perceives and re-reasons about this loan right now, without acting">
        <Async state={loans}>
          {(p) => (
            <label className="block"><span className="sr-only">Loan</span>
              <select className="input" value={id ?? ""} onChange={(e) => setId(Number(e.target.value))}>
                {p.items.map((l) => <option key={l.id} value={l.id}>#{l.id} · {l.title} — {l.member_name} · {(l.days_overdue ?? 0) > 0 ? `${l.days_overdue}d overdue` : `due in ${l.days_until_due}d`}</option>)}
              </select>
            </label>
          )}
        </Async>
      </Card>
      {error && <ErrorState message={error} />}
      {!data && !error && id && <Spinner />}
      {data && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Perceived facts" subtitle={data.label}>
            <KeyValue items={Object.entries(data.facts).map(([k, v]) => [<span key={k} className="font-mono text-xs">{k}</span>, <span key={`${k}v`} className="font-mono text-xs">{String(v)}</span>])} />
            <p className="eyebrow mb-1 mt-4">Asserted conclusions</p>
            <div className="flex flex-wrap gap-1">{data.asserted.length ? data.asserted.map((a) => <code key={a} className="rounded bg-accent/10 px-1.5 py-0.5 font-mono text-[11px] text-accent">{a}</code>) : <span className="text-sm text-muted">None</span>}</div>
          </Card>
          <Card title="Rules fired (forward chaining)"><RuleTrace firings={data.firings} /></Card>
          <Card title={<span className="flex items-center gap-2">Priority <LevelBadge level={data.priority.level} /></span>} subtitle={data.notification_kind ? `Would send: ${KIND_LABELS[data.notification_kind]}` : "No notification rule matches today (scored as if one did)"}>
            <ScoreBreakdown items={data.priority.breakdown} score={data.priority.score} />
          </Card>
          <Card title="Fuzzy classification"><FuzzyView fuzzy={data.priority.fuzzy} /></Card>
          <Card title="Fine (deterministic)"><FineStatement breakdown={data.fine} /></Card>
          <Card title="Prediction factors"><PredictionFactors prediction={data.prediction} /></Card>
        </div>
      )}
    </div>
  );
}

function NotificationExplorer({ initialId }: { initialId: number | null }) {
  const { tick } = useAgent();
  const list = useApi<Page<Notification>>(`/api/notifications${qs({ status: "delivered", page_size: 60 })}`, [tick]);
  const [id, setId] = useState<number | null>(initialId);
  useEffect(() => { if (initialId) setId(initialId); }, [initialId]);
  useEffect(() => { if (!id && list.data?.items.length) setId(list.data.items[0].id); }, [list.data, id]);
  const detail = useApi<Notification>(id ? `/api/notifications/${id}` : null);
  return (
    <div className="grid gap-6 xl:grid-cols-[320px,1fr]">
      <Card title="Recent notifications" bodyClass="p-2">
        <Async state={list} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="No notifications yet" />}>
          {(p) => (
            <ul className="max-h-[70vh] space-y-1 overflow-y-auto">
              {(id && !p.items.some((n) => n.id === id) && detail.data ? [detail.data, ...p.items] : p.items).map((n) => (
                <li key={n.id}><button onClick={() => setId(n.id)} aria-current={n.id === id} className={cx("w-full rounded-lg px-3 py-2 text-left text-sm", n.id === id ? "bg-sunken ring-1 ring-ink" : "hover:bg-sunken")}>
                  <span className="flex items-center gap-2"><LevelBadge level={n.level} /><span className="text-xs text-muted">{fmtDate(n.created_on)}</span></span>
                  <span className="mt-1 block truncate">{n.member_name} · {KIND_LABELS[n.kind]}</span></button></li>
              ))}
            </ul>
          )}
        </Async>
      </Card>
      <Card title="Explanation">
        {!id ? <EmptyState title="Pick a notification" /> : <Async state={detail}>{(n) => (
          <div className="space-y-4">
            <div><div className="flex flex-wrap gap-2"><LevelBadge level={n.level} score={n.score} /><StatusBadge status={n.status} /></div><p className="mt-1 font-medium">{n.subject}</p><p className="text-sm text-ink2">{n.body}</p></div>
            {n.explanation ? <NotificationExplanation exp={n.explanation} /> : <Notice>No explanation stored.</Notice>}
          </div>
        )}</Async>}
      </Card>
    </div>
  );
}

interface Curves { curves: Record<string, { label: string; sets: string[]; points: Record<string, number>[] }>; rules: { id: string; if: string; then: Level }[] }

function FuzzyPlayground() {
  const model = useApi<Curves>("/api/explain/fuzzy");
  const [inp, setInp] = useState({ lateness: 8, demand: 3, fine: 40, risk: 0.4 });
  const [result, setResult] = useState<FuzzyResult | null>(null);
  useEffect(() => {
    const t = window.setTimeout(() => {
      get<FuzzyResult>(`/api/explain/fuzzy/evaluate${qs(inp)}`).then(setResult).catch(() => null);
    }, 200);
    return () => window.clearTimeout(t);
  }, [inp]);
  const sliders: { key: keyof typeof inp; label: string; min: number; max: number; step: number; fmt: (v: number) => string }[] = [
    { key: "lateness", label: "Lateness (days, negative = days left)", min: -7, max: 25, step: 1, fmt: (v) => (v < 0 ? `${-v} days left` : `${v} days overdue`) },
    { key: "demand", label: "Members waiting", min: 0, max: 6, step: 1, fmt: (v) => `${v}` },
    { key: "fine", label: "Fine amount", min: 0, max: 600, step: 10, fmt: (v) => rupees(v) },
    { key: "risk", label: "Predicted risk", min: 0, max: 1, step: 0.05, fmt: (v) => `${Math.round(v * 100)}%` },
  ];
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr,1.2fr]">
      <div className="space-y-6">
        <Card title="Try the fuzzy classifier" subtitle="Move the inputs; the backend fuzzifies, fires rules (min/max) and picks a level">
          <div className="space-y-4">
            {sliders.map((s) => (
              <div key={s.key}>
                <label className="flex justify-between text-sm" htmlFor={`fz-${s.key}`}><span>{s.label}</span><span className="num font-mono">{s.fmt(inp[s.key])}</span></label>
                <input id={`fz-${s.key}`} type="range" min={s.min} max={s.max} step={s.step} value={inp[s.key]} className="w-full accent-[rgb(var(--accent))]"
                  onChange={(e) => setInp({ ...inp, [s.key]: Number(e.target.value) })} />
              </div>
            ))}
          </div>
          {result && <div className="mt-4 flex items-center gap-3 border-t border-line pt-3"><span className="text-sm text-ink2">Result</span><LevelBadge level={result.level} /><span className="font-mono text-xs text-muted">crisp {result.crisp}</span></div>}
        </Card>
        {result && <Card title="Inference trace"><FuzzyView fuzzy={result} /></Card>}
      </div>
      <div className="space-y-6">
        <Async state={model}>
          {(m) => (
            <>
              {Object.entries(m.curves).map(([variable, c]) => (
                <Card key={variable} title={c.label} subtitle="Membership functions (triangular / trapezoidal)">
                  <Legend items={c.sets.map((s, i) => ({ label: humanise(s), color: SERIES[i % SERIES.length] }))} />
                  <div className="h-44">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={c.points} margin={{ top: 6, right: 12, bottom: 0, left: -24 }}>
                        <CartesianGrid {...gridProps} />
                        <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} {...axisProps} />
                        <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} {...axisProps} axisLine={false} />
                        <Tooltip content={<ChartTooltip format={(v) => v.toFixed(2)} />} labelFormatter={(x) => `x = ${x}`} />
                        {c.sets.map((s, i) => <Line key={s} dataKey={s} name={humanise(s)} type="linear" stroke={SERIES[i % SERIES.length]} strokeWidth={2} dot={false} isAnimationActive={false} />)}
                        <ReferenceLine x={inp[variable as keyof typeof inp]} stroke="rgb(var(--ink))" strokeWidth={1} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              ))}
              <Card title="Fuzzy rule base">
                <ul className="space-y-1 text-sm">{m.rules.map((r) => <li key={r.id} className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-muted">{r.id}</span>IF {r.if} → <LevelBadge level={r.then} /></li>)}</ul>
              </Card>
            </>
          )}
        </Async>
      </div>
    </div>
  );
}
