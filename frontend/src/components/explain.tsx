import { ArrowRight, GitBranch } from "lucide-react";
import type { Explanation, FineBreakdown, Firing, FuzzyResult, Prediction, ScoreItem } from "../lib/types";
import { CHANNEL_LABELS, fmtDate, humanise, rupees } from "../lib/format";
import { LEVEL_COLORS, SERIES } from "./charts";
import { LevelBadge, StatusBadge, TableWrap, cx } from "./ui";

/** Weighted-utility breakdown as a stacked bar + table. */
export function ScoreBreakdown({ items, score }: { items: ScoreItem[]; score: number }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm text-ink2">Utility score = Σ weight × normalised factor</span>
        <span className="num font-display text-2xl font-semibold">{score.toFixed(1)}<span className="text-sm text-muted">/100</span></span>
      </div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded-full bg-sunken" role="img" aria-label={`Score ${score} of 100`}>
        {items.filter((i) => i.contribution > 0).map((i, idx) => (
          <span key={i.factor} title={`${i.label}: ${i.contribution}`} style={{ width: `${i.contribution}%`, background: SERIES[idx % SERIES.length] }} />
        ))}
      </div>
      <TableWrap label="Score breakdown">
        <table className="table-base num mt-3">
          <thead><tr><th>Factor</th><th>Raw input</th><th>Normalised</th><th>Weight</th><th className="text-right">Points</th></tr></thead>
          <tbody>
            {items.map((i, idx) => (
              <tr key={i.factor}>
                <td><span className="mr-2 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: SERIES[idx % SERIES.length] }} aria-hidden />{i.label}</td>
                <td className="font-mono text-xs">{typeof i.raw === "number" ? (Number.isInteger(i.raw) ? i.raw : (i.raw as number).toFixed(2)) : humanise(String(i.raw))}</td>
                <td className="font-mono text-xs">{i.normalised.toFixed(2)}</td>
                <td className="font-mono text-xs">{i.weight.toFixed(1)}</td>
                <td className="text-right font-mono">{i.contribution.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </div>
  );
}

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <span className="relative inline-block h-2 w-24 overflow-hidden rounded-full bg-sunken align-middle" aria-hidden>
      <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${value * 100}%`, background: color }} />
    </span>
  );
}

/** Fuzzification → rule activations → aggregated output levels. */
export function FuzzyView({ fuzzy }: { fuzzy: FuzzyResult }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {Object.entries(fuzzy.memberships).map(([variable, sets]) => (
          <div key={variable} className="rounded-lg border border-line p-3">
            <p className="mb-2 flex items-baseline justify-between text-sm">
              <span className="font-medium capitalize">{variable}</span>
              <span className="font-mono text-xs text-muted">input = {fuzzy.inputs[variable] === null ? "n/a" : fuzzy.inputs[variable]}</span>
            </p>
            <ul className="space-y-1">
              {Object.entries(sets).map(([name, mu]) => (
                <li key={name} className={cx("flex items-center justify-between gap-2 text-xs", mu > 0 ? "text-ink" : "text-muted")}>
                  <span>{humanise(name)}</span>
                  <span className="flex items-center gap-2"><Bar value={mu} color="rgb(var(--teal))" /><span className="num w-10 text-right font-mono">{mu.toFixed(2)}</span></span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div>
        <p className="eyebrow mb-1">Fired fuzzy rules (AND = min, OR = max)</p>
        {fuzzy.activations.length === 0 ? <p className="text-sm text-muted">No fuzzy rule fired — defaults to Low.</p> : (
          <ul className="space-y-1 text-sm">
            {fuzzy.activations.map((a) => (
              <li key={a.rule} className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted">{a.rule}</span>
                <span>IF {a.if}</span>
                <ArrowRight className="h-3.5 w-3.5 text-muted" aria-hidden />
                <LevelBadge level={a.then} />
                <span className="num font-mono text-xs text-ink2">μ = {a.strength.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="eyebrow mb-1">Aggregated output strength</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {(["Critical", "High", "Medium", "Low"] as const).map((lv) => (
            <div key={lv} className={cx("rounded-lg border px-3 py-2", fuzzy.level === lv ? "border-ink" : "border-line")}>
              <p className="text-xs text-muted">{lv}{fuzzy.level === lv ? " — winner" : ""}</p>
              <p className="flex items-center gap-2"><Bar value={fuzzy.output_strengths[lv] ?? 0} color={LEVEL_COLORS[lv]} /><span className="num font-mono text-sm">{(fuzzy.output_strengths[lv] ?? 0).toFixed(2)}</span></p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-ink2">
          Defuzzified (weighted centroid of Low 15 · Medium 40 · High 65 · Critical 90): <span className="font-mono">{fuzzy.crisp}</span>
          {fuzzy.floor_applied && <> · <strong>{fuzzy.floor_applied}</strong></>}
        </p>
      </div>
    </div>
  );
}

/** Forward-chaining trace: which rules fired, on which facts, in which iteration. */
export function RuleTrace({ firings, compact }: { firings: Firing[]; compact?: boolean }) {
  if (!firings?.length) return <p className="text-sm text-muted">No rules fired.</p>;
  return (
    <ol className="space-y-2">
      {firings.map((f, i) => (
        <li key={`${f.rule_code}-${f.entity_id ?? ""}-${i}`} className="rounded-lg border border-line bg-sunken/40 p-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <GitBranch className="h-3.5 w-3.5 text-teal" aria-hidden />
            <span className="font-mono text-xs font-medium">{f.rule_code}</span>
            <span className="text-ink2">{f.rule_name}</span>
            {f.iteration !== undefined && <span className="ml-auto font-mono text-[11px] text-muted">iteration {f.iteration}{f.salience !== undefined ? ` · salience ${f.salience}` : ""}</span>}
          </div>
          <div className={cx("mt-1.5 flex flex-wrap items-center gap-1.5 text-xs", compact && "hidden sm:flex")}>
            <span className="text-muted">IF</span>
            {f.matched.map((m, j) => (
              <span key={j} className="inline-flex items-center gap-1">
                {j > 0 && <span className="text-muted">AND</span>}
                <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-[11px] ring-1 ring-line">{m.condition}</code>
                <span className="text-muted">(={String(m.actual)})</span>
              </span>
            ))}
            <span className="text-muted">THEN assert</span>
            <code className="rounded bg-accent/10 px-1.5 py-0.5 font-mono text-[11px] font-medium text-accent ring-1 ring-accent/30">{f.asserted}</code>
          </div>
        </li>
      ))}
    </ol>
  );
}

const LINE_STYLE: Record<string, string> = { grace: "text-teal", holiday: "text-muted", sunday: "text-muted", charged: "", capped: "text-crit" };

/** Day-by-day fine statement. */
export function FineStatement({ breakdown }: { breakdown: FineBreakdown }) {
  const p = breakdown.policy;
  return (
    <div className="space-y-3">
      <p className="text-sm">{breakdown.summary}</p>
      {p && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-md bg-sunken px-2 py-1">{humanise(p.member_type)} policy</span>
          <span className="rounded-md bg-sunken px-2 py-1">Grace {p.grace_days} day(s)</span>
          {p.fine_slabs.map((s) => (
            <span key={s.from_day} className="rounded-md bg-sunken px-2 py-1">Days {s.from_day}{s.to_day ? `–${s.to_day}` : "+"}: {rupees(s.rate)}/day</span>
          ))}
          <span className="rounded-md bg-sunken px-2 py-1">Cap {rupees(p.max_fine)}</span>
          {p.exclude_sundays && <span className="rounded-md bg-sunken px-2 py-1">Sundays free</span>}
        </div>
      )}
      {breakdown.lines.length > 0 ? (
        <TableWrap label="Day-by-day fine">
          <table className="table-base num">
            <thead><tr><th>Date</th><th>Overdue day</th><th>Treatment</th><th>Chargeable #</th><th className="text-right">Charge</th><th className="text-right">Running total</th></tr></thead>
            <tbody>
              {breakdown.lines.map((l) => (
                <tr key={l.date}>
                  <td className="whitespace-nowrap">{fmtDate(l.date, { weekday: "short", day: "numeric", month: "short" })}</td>
                  <td className="font-mono text-xs">{l.overdue_day}</td>
                  <td className={cx("text-xs", LINE_STYLE[l.status])}>{l.note}</td>
                  <td className="font-mono text-xs">{l.chargeable_index ?? "—"}</td>
                  <td className="text-right font-mono">{l.amount ? rupees(l.amount) : "—"}</td>
                  <td className="text-right font-mono">{rupees(l.cumulative)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : <p className="text-sm text-muted">Not overdue — no fine.</p>}
      {breakdown.extra_charges.length > 0 && (
        <ul className="space-y-1 text-sm">
          {breakdown.extra_charges.map((e) => <li key={e.label} className="flex justify-between"><span>{e.label}</span><span className="font-mono">{rupees(e.amount)}</span></li>)}
        </ul>
      )}
      <p className="flex justify-between border-t border-line pt-2 font-medium"><span>Total assessed</span><span className="num font-mono">{rupees(breakdown.total)}</span></p>
      <p className="text-xs text-muted">Computed deterministically from policy and dates only. Machine-learning predictions are never used to set fines.</p>
    </div>
  );
}

export function PredictionFactors({ prediction }: { prediction: Partial<Prediction> | null | undefined }) {
  if (!prediction || prediction.probability === undefined) return <p className="text-sm text-muted">No prediction recorded for this loan.</p>;
  const isTree = prediction.model?.algo === "decision_tree";
  return (
    <div className="space-y-2">
      <p className="text-sm">
        <span className="num font-display text-2xl font-semibold">{Math.round(prediction.probability * 100)}%</span>{" "}
        <span className="text-ink2">late-return risk ({prediction.label}) · {isTree ? "Decision Tree" : "Logistic Regression"} v{prediction.model?.version}</span>
      </p>
      {isTree ? (
        <ol className="space-y-1 text-sm">
          {(prediction.factors ?? []).map((f, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-muted">{i + 1}.</span><span>{f.text}</span>
              {f.risk_after_step !== undefined && <span className="font-mono text-xs text-ink2">→ {Math.round(f.risk_after_step * 100)}% of similar loans were late</span>}
            </li>
          ))}
        </ol>
      ) : (
        <ul className="space-y-1 text-sm">
          {(prediction.factors ?? []).map((f, i) => (
            <li key={i} className="flex items-center justify-between gap-2">
              <span>{f.text}</span>
              <span className={cx("num font-mono text-xs", (f.contribution ?? 0) > 0 ? "text-crit" : "text-good")}>
                {(f.contribution ?? 0) > 0 ? "▲ raises" : "▼ lowers"} {Math.abs(f.contribution ?? 0).toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">Decision support only: it can make a reminder gentler-but-earlier; it never triggers fines, restrictions or lost-book actions.</p>
    </div>
  );
}

/** Full "why was this notification sent" panel. */
export function NotificationExplanation({ exp }: { exp: Explanation }) {
  return (
    <div className="space-y-5">
      <p className="rounded-lg bg-sunken/70 p-3 text-sm">{exp.why}</p>
      <section>
        <h3 className="mb-2 font-display text-base font-semibold">1 · Rules that fired (forward chaining)</h3>
        <RuleTrace firings={exp.rules} />
      </section>
      <section>
        <h3 className="mb-2 font-display text-base font-semibold">2 · Priority score (weighted utility)</h3>
        <ScoreBreakdown items={exp.priority.breakdown} score={exp.priority.score} />
      </section>
      <section>
        <h3 className="mb-2 font-display text-base font-semibold">3 · Priority level (fuzzy logic): <LevelBadge level={exp.priority.level} /></h3>
        <FuzzyView fuzzy={exp.priority.fuzzy} />
      </section>
      <section className="grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="mb-2 font-display text-base font-semibold">4 · Channel</h3>
          <p className="text-sm"><StatusBadge status="sent" label={CHANNEL_LABELS[exp.channel.channel] ?? exp.channel.channel} /> <span className="text-ink2">{exp.channel.reason}</span></p>
          <p className="mt-1 text-xs text-muted">Member preference: {CHANNEL_LABELS[exp.channel.preference] ?? exp.channel.preference}</p>
          <p className="mt-1 text-xs text-muted">Heap position when processed: #{exp.queue_rank} · key {exp.queue_key}</p>
        </div>
        <div>
          <h3 className="mb-2 font-display text-base font-semibold">5 · Anti-spam checks</h3>
          <ul className="space-y-0.5 text-sm">{exp.anti_spam.map((c) => <li key={c} className={c.startsWith("✗") ? "text-crit" : ""}>{c}</li>)}</ul>
        </div>
      </section>
      {exp.prediction && (
        <section>
          <h3 className="mb-2 font-display text-base font-semibold">6 · Prediction factors</h3>
          <PredictionFactors prediction={exp.prediction} />
        </section>
      )}
    </div>
  );
}
