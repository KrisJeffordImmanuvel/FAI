import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarPlus, ChevronRight, Pause, Play, PlayCircle, RotateCcw, SkipForward, Sparkles, StepForward, Zap } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { get, post, put } from "../lib/api";
import { fmtDate } from "../lib/format";
import type { AgentEvent, AgentSettings, Cycle, DemoState } from "../lib/types";
import { can } from "../lib/roles";
import { Async, Card, EmptyState, Modal, Notice, PageHeader, Spinner, cx } from "../components/ui";
import { useAction } from "../components/toast";
import { EventItem } from "./Dashboard";

export default function AgentControl() {
  return (
    <div>
      <PageHeader eyebrow="Sense · Think · Act" title="Agent control center"
        description="Drive the simulated clock, run the agent one cycle at a time or automatically, and play the guided viva scenario." />
      <div className="grid gap-6 2xl:grid-cols-[1fr,1.1fr]">
        <div className="space-y-6">
          <ClockCard />
          <DemoCard />
        </div>
        <div className="space-y-6">
          <LiveFeed />
          <CyclesCard />
        </div>
      </div>
    </div>
  );
}

function ClockCard() {
  const user = useUser();
  const { status, auto, setAuto, busy, lastError, bump } = useAgent();
  const act = useAction();
  const [working, setWorking] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const settings = useApi<AgentSettings>("/api/admin/settings");

  const run = async (label: string, fn: () => Promise<unknown>, msg: string | ((r: never) => string)) => {
    setWorking(label);
    const r = await act(fn as () => Promise<never>, msg as string);
    setWorking(null);
    if (r !== null) bump();
  };

  async function toggleBackground() {
    if (!settings.data) return;
    const r = await act(() => put<AgentSettings>("/api/admin/settings", { background_activity: !settings.data!.background_activity }), "Simulation setting saved");
    if (r) settings.setData(r);
  }

  return (
    <Card title="Simulated clock" subtitle="Each simulated day runs one full perceive → think → act cycle">
      {!status ? <Spinner /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <p className="eyebrow">Today in the simulation</p>
              <p className="font-display text-4xl font-semibold leading-tight">{fmtDate(status.sim_date, { day: "numeric", month: "long", year: "numeric" })}</p>
              <p className="text-sm text-ink2">{status.weekday} · {status.cycles} cycles run · {status.pending_approvals} approvals pending</p>
            </div>
            {auto && <span className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-accent/15 px-3 py-1 text-sm font-medium text-accent"><Zap className={cx("h-4 w-4", busy && "animate-pulse")} aria-hidden />Auto mode · every {status.auto_interval_sec}s</span>}
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <button className="btn-primary" disabled={!!working || auto} onClick={() => run("run", () => post<Cycle>("/api/agent/run", { mode: "manual" }), "Agent cycle complete")}>
              <PlayCircle className="h-4 w-4" aria-hidden />{working === "run" ? "Running…" : "Run one cycle"}</button>
            <button className="btn-secondary" disabled={!!working || auto} onClick={() => run("d1", () => post("/api/agent/advance", { days: 1, run_agent: true }), "Advanced 1 day and ran the agent")}>
              <StepForward className="h-4 w-4" aria-hidden />{working === "d1" ? "Advancing…" : "+1 day"}</button>
            <button className="btn-secondary" disabled={!!working || auto} onClick={() => run("d7", () => post("/api/agent/advance", { days: 7, run_agent: true }), "Advanced 7 days (7 agent cycles)")}>
              <CalendarPlus className="h-4 w-4" aria-hidden />{working === "d7" ? "Advancing…" : "+7 days"}</button>
            <button className={auto ? "btn-danger" : "btn-secondary"} disabled={!!working} onClick={() => setAuto(!auto)} aria-pressed={auto}>
              {auto ? <><Pause className="h-4 w-4" aria-hidden />Stop auto mode</> : <><Play className="h-4 w-4" aria-hidden />Start auto mode</>}</button>
            <button className="btn-ghost sm:col-span-2 lg:col-span-2" disabled={!!working || auto} onClick={() => setConfirmReset(true)}><RotateCcw className="h-4 w-4" aria-hidden />Reset simulation to the seeded state</button>
          </div>
          {lastError && <Notice tone="error">Auto mode stopped: {lastError}</Notice>}
          {status.last_cycle && <p className="text-xs text-muted">Last cycle #{status.last_cycle.id} ({status.last_cycle.duration_ms} ms): {status.last_cycle.summary}</p>}
          {can.editSettings(user.role) && settings.data && (
            <label className="flex items-start gap-2 rounded-lg border border-line p-3 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--accent))]" checked={settings.data.background_activity} onChange={toggleBackground} />
              <span><span className="font-medium">Simulate member activity when the clock advances</span>
                <span className="block text-xs text-muted">Seeded random returns, pickups, checkouts and reservations each day, so the environment keeps changing in auto mode.</span></span>
            </label>
          )}
        </div>
      )}
      <Modal open={confirmReset} onClose={() => setConfirmReset(false)} title="Reset the simulation?">
        <p className="text-sm">This re-runs the deterministic seeder: all data returns to 2 November 2026 with the original books, members, history and models. It takes about 10 seconds.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setConfirmReset(false)}>Cancel</button>
          <button className="btn-danger" onClick={() => { setConfirmReset(false); setAuto(false); void run("reset", () => post("/api/agent/reset"), "Simulation reset to the seeded state"); }}>Reset</button>
        </div>
      </Modal>
      {working === "reset" && <Notice tone="info">Re-seeding the database…</Notice>}
    </Card>
  );
}

function DemoCard() {
  const { bump } = useAgent();
  const state = useApi<DemoState>("/api/demo");
  const act = useAction();
  const [working, setWorking] = useState(false);
  const [autoplay, setAutoplay] = useState(false);
  const autoRef = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);

  const step = useCallback(async (start: boolean) => {
    setWorking(true);
    const r = await act(() => post<DemoState>(start ? "/api/demo/start" : "/api/demo/next"));
    setWorking(false);
    if (r) { state.setData(r); bump(); }
    return r;
  }, [act, bump, state]);

  async function playAll() {
    autoRef.current = true;
    setAutoplay(true);
    let r = await step(true);
    while (r && autoRef.current && r.state && r.state.step < r.steps.length - 1) {
      await new Promise((res) => setTimeout(res, 1600));
      if (!autoRef.current) break;
      r = await step(false);
    }
    autoRef.current = false;
    setAutoplay(false);
  }

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [state.data?.state?.log.length]);
  useEffect(() => () => { autoRef.current = false; }, []);

  return (
    <Card title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-accent" aria-hidden />Guided demo scenario</span>}
      subtitle="A reserved book becomes overdue → priority rises → notification → fine → return → allocation to the next member">
      <Async state={state}>
        {(d) => {
          const done = d.state ? d.state.step >= d.steps.length - 1 : false;
          const current = d.state ? d.state.step : -1;
          return (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <button className="btn-primary" disabled={working} onClick={playAll}><Play className="h-4 w-4" aria-hidden />{autoplay ? "Playing…" : "Play full demo"}</button>
                {autoplay ? <button className="btn-secondary" onClick={() => { autoRef.current = false; }}><Pause className="h-4 w-4" aria-hidden />Pause</button> : (
                  <>
                    <button className="btn-secondary" disabled={working} onClick={() => step(true)}><RotateCcw className="h-4 w-4" aria-hidden />{d.state ? "Restart" : "Start"} step-by-step</button>
                    <button className="btn-secondary" disabled={working || !d.state || done} onClick={() => step(false)}><SkipForward className="h-4 w-4" aria-hidden />Next step</button>
                  </>
                )}
              </div>
              <ol className="grid gap-1.5 sm:grid-cols-2" aria-label="Demo steps">
                {d.steps.map((s, i) => (
                  <li key={s.title} className={cx("flex gap-2 rounded-lg border px-3 py-2 text-xs", i <= current ? "border-teal/40 bg-teal/5" : i === current + 1 ? "border-accent/50" : "border-line text-muted")}>
                    <span className={cx("flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[10px]", i <= current ? "bg-teal text-white" : "bg-sunken")}>{i}</span>
                    <span>{s.title}</span>
                  </li>
                ))}
              </ol>
              {!d.state ? <EmptyState title="Demo not started">Uses the single demo copy of “Artificial Intelligence: A Modern Approach”, student Aarav Sharma (member@library.local) and Dr. Meera Iyer.</EmptyState> : (
                <ol className="relative space-y-4 border-l-2 border-line pl-5" aria-live="polite">
                  {d.state.log.map((entry) => (
                    <li key={entry.step} className="animate-slide-in">
                      <span className="absolute -left-[9px] mt-1 h-4 w-4 rounded-full border-2 border-surface bg-accent" aria-hidden />
                      <p className="eyebrow">Step {entry.step} · {fmtDate(entry.sim_date)}</p>
                      <h3 className="font-display text-base font-semibold">{entry.title}</h3>
                      <ul className="mt-1 space-y-1 text-sm">{entry.narrative.map((n, i) => <li key={i} className="flex gap-1.5"><ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden /><span>{n}</span></li>)}</ul>
                      {entry.events && entry.events.length > 0 && (
                        <details className="mt-1.5"><summary className="cursor-pointer text-xs text-ink2">{entry.events.length} agent events during this step</summary>
                          <ul className="mt-1 divide-y divide-line">{entry.events.map((e) => <EventItem key={e.id} e={e} />)}</ul></details>
                      )}
                      <div className="mt-1.5 flex flex-wrap gap-2 text-xs">
                        {Array.isArray(entry.refs.cycle_ids) && (entry.refs.cycle_ids as number[]).map((c) => <Link key={c} className="underline" to={`/explain?cycle=${c}`}>Explain cycle #{c}</Link>)}
                        {Array.isArray(entry.refs.notification_ids) && (entry.refs.notification_ids as number[]).length > 0 && <Link className="underline" to="/notifications">Open notifications</Link>}
                        {typeof entry.refs.fine_id === "number" && <Link className="underline" to="/fines">Fine statement</Link>}
                      </div>
                    </li>
                  ))}
                  {done && <li><Notice tone="success">Scenario complete. Sign in as <span className="font-mono">member@library.local</span> to see Aarav's recall messages, or open Explainability.</Notice></li>}
                </ol>
              )}
              <div ref={bottom} />
            </div>
          );
        }}
      </Async>
    </Card>
  );
}

const PHASES = ["", "perceive", "think", "act", "human", "system", "demo"] as const;

function LiveFeed() {
  const { tick } = useAgent();
  const [events, setEvents] = useState<AgentEvent[] | null>(null);
  const [phase, setPhase] = useState<(typeof PHASES)[number]>("");
  const [error, setError] = useState<string | null>(null);
  const lastId = useRef(0);

  useEffect(() => {
    lastId.current = 0;
    setEvents(null);
    get<AgentEvent[]>(`/api/agent/events?limit=60${phase ? `&phase=${phase}` : ""}`)
      .then((ev) => { setEvents(ev.reverse()); lastId.current = ev.reduce((m, e) => Math.max(m, e.id), 0); setError(null); })
      .catch((e) => setError(e.message));
  }, [phase]);

  useEffect(() => {
    const poll = async () => {
      if (!lastId.current) return;
      try {
        const ev = await get<AgentEvent[]>(`/api/agent/events?after_id=${lastId.current}&limit=200${phase ? `&phase=${phase}` : ""}`);
        if (ev.length) {
          lastId.current = ev[ev.length - 1].id;
          setEvents((cur) => [...ev.reverse(), ...(cur ?? [])].slice(0, 200));
        }
      } catch { /* transient */ }
    };
    void poll();
    const id = window.setInterval(poll, 3000);
    return () => window.clearInterval(id);
  }, [phase, tick]);

  return (
    <Card title="Live decision feed" subtitle="Every percept, inference, action and human decision — newest first"
      actions={<label><span className="sr-only">Phase filter</span><select className="input py-1 text-xs" value={phase} onChange={(e) => setPhase(e.target.value as typeof phase)}>
        {PHASES.map((p) => <option key={p} value={p}>{p ? p[0].toUpperCase() + p.slice(1) : "All phases"}</option>)}</select></label>}>
      {error ? <Notice tone="error">{error}</Notice> : !events ? <Spinner /> : events.length === 0 ? <EmptyState title="No events yet">Run a cycle to see the agent think.</EmptyState> : (
        <ul className="max-h-[560px] divide-y divide-line overflow-y-auto pr-1" aria-live="polite">{events.map((e) => <EventItem key={e.id} e={e} />)}</ul>
      )}
    </Card>
  );
}

function CyclesCard() {
  const { tick } = useAgent();
  const state = useApi<Cycle[]>("/api/agent/cycles?limit=12", [tick]);
  return (
    <Card title="Recent cycles" subtitle="Stored percepts, rule firings, decisions and actions">
      <Async state={state} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No cycles yet" />}>
        {(cycles) => (
          <ul className="divide-y divide-line">
            {cycles.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="font-mono text-xs text-muted">#{c.id}</span>
                <span className="rounded bg-sunken px-1.5 font-mono text-[10px] uppercase">{c.mode}</span>
                <span className="min-w-0 flex-1">{c.summary}</span>
                <Link className="btn-ghost px-2 py-1 text-xs" to={`/explain?cycle=${c.id}`}>Explain</Link>
              </li>
            ))}
          </ul>
        )}
      </Async>
    </Card>
  );
}
