import { useEffect, useState } from "react";
import { FlaskConical, Pencil, Plus, RotateCcw, ShieldAlert, Trash2 } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useApi } from "../lib/useApi";
import { del, post, put } from "../lib/api";
import { humanise } from "../lib/format";
import type { Condition, Firing, KbSchema, Rule } from "../lib/types";
import { can } from "../lib/roles";
import { Async, Card, Field, Modal, Notice, PageHeader, Tabs, cx } from "../components/ui";
import { RuleTrace } from "../components/explain";
import { useAction } from "../components/toast";

const BOOL_OPS = ["is_true", "is_false"];

function describe(c: Condition): string {
  if (BOOL_OPS.includes(c.op)) return `${c.field} ${c.op === "is_true" ? "is true" : "is false"}`;
  return `${c.field} ${c.op} ${c.value_field ?? JSON.stringify(c.value)}`;
}

export default function KnowledgeBase() {
  const user = useUser();
  const editable = can.editKnowledgeBase(user.role);
  const rules = useApi<{ items: Rule[]; tainted: Record<string, string> }>("/api/kb/rules");
  const schema = useApi<KbSchema>("/api/kb/schema");
  const [entity, setEntity] = useState("loan");
  const [editing, setEditing] = useState<Partial<Rule> | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const act = useAction();

  async function toggle(r: Rule) {
    const res = await act(() => put(`/api/kb/rules/${r.id}`, { ...strip(r), enabled: !r.enabled }), `${r.code} ${r.enabled ? "disabled" : "enabled"}`);
    if (res) rules.reload();
  }
  async function remove(r: Rule) {
    if (!window.confirm(`Delete rule ${r.code}? The agent will stop using it immediately.`)) return;
    const res = await act(() => del(`/api/kb/rules/${r.id}`).then(() => true), `${r.code} deleted`);
    if (res) rules.reload();
  }
  async function reset() {
    const res = await act(() => post("/api/kb/reset"), "Knowledge base restored to the default rules");
    setConfirmReset(false);
    if (res) rules.reload();
  }

  return (
    <div>
      <PageHeader eyebrow="Expert system" title="Knowledge base"
        description="Production rules stored as editable data. The forward-chaining engine fires them by salience until no new facts can be derived."
        actions={editable && <>
          <button className="btn-secondary" onClick={() => setConfirmReset(true)}><RotateCcw className="h-4 w-4" aria-hidden />Restore defaults</button>
          <button className="btn-primary" onClick={() => setEditing({ entity, conditions: [{ field: "", op: ">", value: 0 }], salience: 50, enabled: true })}><Plus className="h-4 w-4" aria-hidden />New rule</button>
        </>} />
      {!editable && <div className="mb-4"><Notice>You can view and test rules. Only administrators can edit the knowledge base.</Notice></div>}
      <div className="mb-4"><Tabs label="Entity" value={entity} onChange={setEntity} options={["loan", "member", "reservation", "fine"].map((e) => ({ value: e, label: `${humanise(e)} rules` }))} /></div>
      <div className="grid gap-6 2xl:grid-cols-[1.5fr,1fr]">
        <Async state={rules}>
          {(d) => (
            <ul className="space-y-2">
              {d.items.filter((r) => r.entity === entity).map((r) => {
                const meta = schema.data?.conclusions[r.conclusion];
                return (
                  <li key={r.id} className={cx("card p-4", !r.enabled && "opacity-60")}>
                    <div className="flex flex-wrap items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs font-medium">{r.code}</span><span className="font-medium">{r.name}</span>
                          <span className="rounded bg-sunken px-1.5 font-mono text-[10px]">salience {r.salience}</span>
                          {meta?.approval && <span className="rounded bg-teal/10 px-1.5 text-[10px] font-medium text-teal">needs human approval</span>}
                          {d.tainted[r.conclusion] && <span className="rounded bg-med/20 px-1.5 text-[10px] font-medium" title="Depends on the ML prediction">advisory (uses prediction)</span>}</p>
                        <p className="mt-0.5 text-sm text-ink2">{r.description}</p>
                      </div>
                      {editable && (
                        <div className="flex gap-1">
                          <label className="btn-ghost cursor-pointer px-2 py-1 text-xs"><input type="checkbox" className="mr-1 accent-[rgb(var(--accent))]" checked={r.enabled} onChange={() => toggle(r)} />Enabled</label>
                          <button className="btn-ghost px-2 py-1" onClick={() => setEditing(r)} aria-label={`Edit ${r.code}`}><Pencil className="h-3.5 w-3.5" /></button>
                          <button className="btn-ghost px-2 py-1" onClick={() => remove(r)} aria-label={`Delete ${r.code}`}><Trash2 className="h-3.5 w-3.5" /></button>
                        </div>
                      )}
                    </div>
                    <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="font-mono text-muted">IF</span>
                      {r.conditions.map((c, i) => (
                        <span key={i} className="inline-flex items-center gap-1.5">{i > 0 && <span className="font-mono text-muted">AND</span>}
                          <code className="rounded bg-sunken px-1.5 py-0.5 font-mono">{describe(c)}</code></span>
                      ))}
                      <span className="font-mono text-muted">THEN</span>
                      <code className={cx("rounded px-1.5 py-0.5 font-mono font-medium", meta?.kind === "action" ? "bg-accent/10 text-accent" : "bg-teal/10 text-teal")}>{r.conclusion}</code>
                      {meta && <span className="text-muted">— {meta.label}</span>}
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </Async>
        <div className="space-y-6">
          <Tester entity={entity} schema={schema.data} />
          <Card title={<span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-teal" aria-hidden />Fairness guard</span>}>
            <p className="text-sm text-ink2">When a rule is saved, the system runs a <strong>taint analysis</strong> over the rule graph: any fact derived (directly or through a chain) from <code className="font-mono text-xs">predicted_risk</code> is marked advisory. Penalising conclusions (<code className="font-mono text-xs">RECOMMEND_MARK_LOST</code>, <code className="font-mono text-xs">RECOMMEND_RESTRICTION</code>) are rejected if they depend on an advisory fact.</p>
            {rules.data && <p className="mt-2 text-xs text-muted">Currently advisory: {Object.keys(rules.data.tainted).join(", ") || "none"}</p>}
          </Card>
        </div>
      </div>
      {editing && schema.data && rules.data && <RuleEditor initial={editing} schema={schema.data} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); rules.reload(); }} />}
      <Modal open={confirmReset} onClose={() => setConfirmReset(false)} title="Restore default rules?">
        <p className="text-sm">All custom rules and edits will be replaced by the 19 default rules.</p>
        <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" onClick={() => setConfirmReset(false)}>Cancel</button><button className="btn-danger" onClick={reset}>Restore</button></div>
      </Modal>
    </div>
  );
}

function strip(r: Partial<Rule>) {
  return { code: r.code, name: r.name, description: r.description ?? "", entity: r.entity, conditions: r.conditions, conclusion: r.conclusion, salience: r.salience ?? 50, enabled: r.enabled ?? true };
}

function RuleEditor({ initial, schema, onClose, onSaved }: { initial: Partial<Rule>; schema: KbSchema; onClose: () => void; onSaved: () => void }) {
  const [r, setR] = useState<Partial<Rule>>({ ...initial, conditions: (initial.conditions ?? []).map((c) => ({ ...c })) });
  const [errors, setErrors] = useState<string[]>([]);
  const act = useAction();
  const entity = r.entity ?? "loan";
  const fields = schema.fields[entity] ?? {};
  const factOptions = [...Object.keys(fields), ...Object.keys(schema.conclusions).filter((c) => c !== r.conclusion)];

  function local(): string[] {
    const e: string[] = [];
    if (!/^[A-Za-z0-9_]{2,40}$/.test(r.code ?? "")) e.push("Code: 2–40 letters, digits or underscores");
    if ((r.name ?? "").trim().length < 3) e.push("Name: at least 3 characters");
    if (!r.conclusion) e.push("Choose a conclusion");
    (r.conditions ?? []).forEach((c, i) => {
      if (!c.field) e.push(`Condition ${i + 1}: choose a fact`);
      if (!BOOL_OPS.includes(c.op) && (c.value === "" || c.value === undefined || c.value === null) && !c.value_field) e.push(`Condition ${i + 1}: enter a value`);
    });
    if (!r.conditions?.length) e.push("Add at least one condition");
    return e;
  }

  function setCond(i: number, patch: Partial<Condition>) {
    setR({ ...r, conditions: r.conditions!.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  }

  async function save() {
    const e = local();
    setErrors(e);
    if (e.length) return;
    const body = strip({
      ...r,
      conditions: r.conditions!.map((c) => {
        const out: Condition = { field: c.field, op: c.op };
        if (!BOOL_OPS.includes(c.op)) {
          if (c.value_field) out.value_field = c.value_field;
          else out.value = fields[c.field]?.type === "number" && c.op !== "in" ? Number(c.value) : c.value;
        }
        return out;
      }),
    });
    const v = await act(() => post<{ valid: boolean; errors: string[] }>("/api/kb/validate", body));
    if (!v) return;
    if (!v.valid) { setErrors(v.errors); return; }
    const res = await act(() => (r.id ? put(`/api/kb/rules/${r.id}`, body) : post("/api/kb/rules", body)), `Rule ${body.code} saved — the agent uses it from the next cycle`);
    if (res) onSaved();
  }

  return (
    <Modal open onClose={onClose} title={r.id ? `Edit ${r.code}` : "New rule"} wide>
      <div className="space-y-4">
        {errors.length > 0 && <Notice tone="error"><ul className="list-disc pl-4">{errors.map((e) => <li key={e}>{e}</li>)}</ul></Notice>}
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Code" htmlFor="r-code"><input id="r-code" className="input font-mono" value={r.code ?? ""} onChange={(e) => setR({ ...r, code: e.target.value.toUpperCase() })} disabled={!!r.id} /></Field>
          <div className="sm:col-span-2"><Field label="Name" htmlFor="r-name"><input id="r-name" className="input" value={r.name ?? ""} onChange={(e) => setR({ ...r, name: e.target.value })} /></Field></div>
          <Field label="Salience" htmlFor="r-sal" hint="Higher fires first"><input id="r-sal" type="number" min={0} max={1000} className="input" value={r.salience ?? 50} onChange={(e) => setR({ ...r, salience: Number(e.target.value) })} /></Field>
          <Field label="Entity" htmlFor="r-ent"><select id="r-ent" className="input" value={entity} onChange={(e) => setR({ ...r, entity: e.target.value, conditions: [{ field: "", op: ">", value: 0 }] })} disabled={!!r.id}>
            {schema.entities.map((x) => <option key={x} value={x}>{humanise(x)}</option>)}</select></Field>
          <div className="sm:col-span-3"><Field label="Description" htmlFor="r-desc"><input id="r-desc" className="input" value={r.description ?? ""} maxLength={500} onChange={(e) => setR({ ...r, description: e.target.value })} /></Field></div>
        </div>
        <div>
          <p className="label">IF all of these hold</p>
          <ul className="space-y-2">
            {r.conditions!.map((c, i) => (
              <li key={i} className="grid gap-2 rounded-lg border border-line p-2 sm:grid-cols-[1.4fr,1fr,1.2fr,auto]">
                <label><span className="sr-only">Fact</span><select className="input" value={c.field} onChange={(e) => setCond(i, { field: e.target.value })}>
                  <option value="">Choose a fact…</option>
                  <optgroup label="Perceived facts">{Object.entries(fields).map(([k, f]) => <option key={k} value={k}>{k} — {f.label}</option>)}</optgroup>
                  <optgroup label="Derived facts (chaining)">{factOptions.filter((k) => !(k in fields)).map((k) => <option key={k} value={k}>{k}</option>)}</optgroup>
                </select></label>
                <label><span className="sr-only">Operator</span><select className="input" value={c.op} onChange={(e) => setCond(i, { op: e.target.value })}>
                  {Object.entries(schema.operators).map(([k, v]) => <option key={k} value={k}>{k} ({v})</option>)}</select></label>
                {BOOL_OPS.includes(c.op) ? <span className="self-center text-xs text-muted">no value needed</span> : (
                  <div className="flex gap-1">
                    <label className="flex-1"><span className="sr-only">Value</span><input className="input" placeholder="value" value={c.value_field ? "" : String(c.value ?? "")} disabled={!!c.value_field} onChange={(e) => setCond(i, { value: e.target.value })} /></label>
                    <label><span className="sr-only">or compare with fact</span><select className="input w-32" value={c.value_field ?? ""} onChange={(e) => setCond(i, { value_field: e.target.value || null })}>
                      <option value="">…or a fact</option>{Object.keys(fields).map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
                  </div>
                )}
                <button className="btn-ghost px-2" onClick={() => setR({ ...r, conditions: r.conditions!.filter((_, j) => j !== i) })} aria-label={`Remove condition ${i + 1}`}><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
          {r.conditions!.length < 8 && <button className="btn-ghost mt-2 text-xs" onClick={() => setR({ ...r, conditions: [...r.conditions!, { field: "", op: ">", value: 0 }] })}><Plus className="h-3.5 w-3.5" aria-hidden />Add condition</button>}
        </div>
        <Field label="THEN assert" htmlFor="r-concl"><select id="r-concl" className="input" value={r.conclusion ?? ""} onChange={(e) => setR({ ...r, conclusion: e.target.value })}>
          <option value="">Choose a conclusion…</option>
          {Object.entries(schema.conclusions).map(([k, v]) => <option key={k} value={k}>{k} — {v.label}{v.penalising ? " (penalising, needs approval)" : ""}</option>)}</select></Field>
        <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save}>Validate & save</button></div>
      </div>
    </Modal>
  );
}

const SAMPLES: Record<string, Record<string, unknown>> = {
  loan: { days_overdue: 9, days_past_grace: 7, days_until_due: -9, reservation_queue: 2, renewals_left: 1, fine_amount: 20, lost_after_days: 30, predicted_risk: 0.7, member_late_rate: 0.3, member_unpaid_fines: 120, member_type: "student" },
  member: { unpaid_fines: 320, overdue_loans: 1, active_loans: 3, late_rate: 0.4, status: "active", fine_notice_threshold: 100, restriction_threshold: 250 },
  reservation: { is_ready: true, is_waiting: false, days_waiting: 6, days_until_expiry: 0, copies_available: 0, queue_position: 0 },
  fine: { balance: 12, is_closed_loan: true, member_late_rate: 0.05, waiver_threshold: 20, has_pending_request: false },
};

function Tester({ entity, schema }: { entity: string; schema: KbSchema | null }) {
  const [text, setText] = useState(() => JSON.stringify(SAMPLES[entity], null, 2));
  const [res, setRes] = useState<{ firings: Firing[]; asserted: string[]; actions: string[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const act = useAction();
  useEffect(() => { setText(JSON.stringify(SAMPLES[entity], null, 2)); setRes(null); }, [entity]);
  async function run() {
    let facts: Record<string, unknown>;
    try { facts = JSON.parse(text); } catch { setErr("Facts must be valid JSON"); return; }
    setErr(null);
    const r = await act(() => post<{ firings: Firing[]; asserted: string[]; actions: string[] }>("/api/kb/test", { entity, facts }));
    if (r) setRes(r);
  }
  return (
    <Card title={<span className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-accent" aria-hidden />Rule sandbox</span>} subtitle={`Run forward chaining on hand-written ${entity} facts — nothing is stored`}>
      <label htmlFor="facts" className="label">Working memory (JSON)</label>
      <textarea id="facts" className="input font-mono text-xs" rows={9} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
      {err && <p className="mt-1 text-xs text-crit">{err}</p>}
      {schema && <p className="mt-1 text-[11px] text-muted">Known facts: {Object.keys(schema.fields[entity] ?? {}).join(", ")}</p>}
      <button className="btn-primary mt-2 w-full" onClick={run}>Run inference</button>
      {res && (
        <div className="mt-4 space-y-3">
          <p className="text-sm">Actions the agent would take: {res.actions.length ? res.actions.map((a) => <code key={a} className="mr-1 rounded bg-accent/10 px-1.5 py-0.5 font-mono text-[11px] text-accent">{a}</code>) : <span className="text-muted">none</span>}</p>
          <RuleTrace firings={res.firings} />
        </div>
      )}
    </Card>
  );
}
