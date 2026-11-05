import { useEffect, useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useApi } from "../lib/useApi";
import { del, post, put } from "../lib/api";
import { KIND_LABELS, fmtDate, humanise } from "../lib/format";
import type { AgentSettings, Policy, Slab, User } from "../lib/types";
import { utilityScore, weightsValid, type Weights } from "../lib/scoring";
import { isEmail, slabErrors } from "../lib/validation";
import { Async, Card, Field, Notice, PageHeader, StatusBadge, TableWrap, Tabs } from "../components/ui";
import { useAction } from "../components/toast";

type Tab = "settings" | "policies" | "holidays" | "users";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("settings");
  return (
    <div>
      <PageHeader eyebrow="System" title="Administration" description="Agent settings, circulation and fine policies, library holidays and staff accounts. Every change is audited." />
      <div className="mb-5"><Tabs label="Admin section" value={tab} onChange={setTab} options={[
        { value: "settings", label: "Agent settings" }, { value: "policies", label: "Policies & fines" }, { value: "holidays", label: "Holidays" }, { value: "users", label: "Users" }]} /></div>
      {tab === "settings" && <SettingsTab />}
      {tab === "policies" && <PoliciesTab />}
      {tab === "holidays" && <HolidaysTab />}
      {tab === "users" && <UsersTab />}
    </div>
  );
}

const SAMPLE = { kind: "recall", daysOverdue: 9, demand: 3, fine: 40, risk: 0.55, lateRate: 0.3 };

function SettingsTab() {
  const state = useApi<AgentSettings>("/api/admin/settings");
  const [s, setS] = useState<AgentSettings | null>(null);
  const act = useAction();
  useEffect(() => { if (state.data) setS(structuredClone(state.data)); }, [state.data]);
  if (!s) return <Async state={state}>{() => null}</Async>;
  const wErr = weightsValid(s.priority_weights as Weights);
  const preview = utilityScore(SAMPLE, s.priority_weights as Weights);
  async function save(e: FormEvent) {
    e.preventDefault();
    if (wErr || !s) return;
    const { sim_date: _ignore, high_risk_threshold: _h, ...body } = s;
    void _ignore; void _h;
    const r = await act(() => put<AgentSettings>("/api/admin/settings", body), "Agent settings saved — used from the next cycle");
    if (r) state.setData(r);
  }
  const num = (k: keyof AgentSettings, label: string, hint: string, step = 1) => (
    <Field label={label} htmlFor={`s-${k}`} hint={hint}><input id={`s-${k}`} type="number" min={0} step={step} className="input" value={s[k] as number} onChange={(e) => setS({ ...s, [k]: Number(e.target.value) })} /></Field>
  );
  return (
    <form onSubmit={save} className="grid gap-6 xl:grid-cols-2" noValidate>
      <Card title="Priority utility weights" subtitle="score = Σ wₖ × factorₖ (weights are rescaled to sum to 100)">
        <div className="space-y-3">
          {Object.entries(s.priority_weights).map(([k, v]) => (
            <div key={k}>
              <label htmlFor={`w-${k}`} className="flex justify-between text-sm"><span>{humanise(k)}</span><span className="num font-mono">{v}</span></label>
              <input id={`w-${k}`} type="range" min={0} max={50} step={1} value={v} className="w-full accent-[rgb(var(--accent))]"
                onChange={(e) => setS({ ...s, priority_weights: { ...s.priority_weights, [k]: Number(e.target.value) } })} />
            </div>
          ))}
          {wErr && <Notice tone="error">{wErr}</Notice>}
          <div className="rounded-lg bg-sunken/70 p-3 text-sm">
            <p className="font-medium">Live preview: recall, 9 days overdue, 3 waiting, ₹40 fine, risk 55%, late rate 30%</p>
            <p className="num mt-1 font-display text-2xl font-semibold">{preview.score.toFixed(1)}<span className="text-sm text-muted">/100</span></p>
            <p className="text-xs text-ink2">{preview.parts.map((p) => `${p.factor} ${p.contribution.toFixed(1)}`).join(" · ")}</p>
          </div>
        </div>
      </Card>
      <div className="space-y-6">
        <Card title="Anti-spam" subtitle="Cooldowns are in simulated days; an escalation in fuzzy level overrides a cooldown">
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(s.cooldown_days).map(([k, v]) => (
              <Field key={k} label={`${KIND_LABELS[k] ?? k} cooldown`} htmlFor={`cd-${k}`}><input id={`cd-${k}`} type="number" min={0} max={30} className="input" value={v}
                onChange={(e) => setS({ ...s, cooldown_days: { ...s.cooldown_days, [k]: Number(e.target.value) } })} /></Field>
            ))}
            {num("daily_limit", "Daily limit per member", "Critical notices always go through")}
            {num("dispatch_capacity", "Dispatch capacity per cycle", "Overflow waits in the heap")}
          </div>
        </Card>
        <Card title="Thresholds & simulation">
          <div className="grid gap-3 sm:grid-cols-2">
            {num("fine_notice_threshold", "Fine notice threshold (₹)", "Rule R20")}
            {num("restriction_fine_threshold", "Restriction suggestion (₹)", "Rule R21 — needs approval")}
            {num("waiver_suggestion_max", "Goodwill waiver max (₹)", "Rule R40 — needs approval")}
            {num("auto_interval_sec", "Auto mode interval (s)", "Seconds between simulated days")}
            <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" className="h-4 w-4 accent-[rgb(var(--accent))]" checked={s.background_activity} onChange={(e) => setS({ ...s, background_activity: e.target.checked })} />Simulate member activity when the clock advances</label>
          </div>
        </Card>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={() => state.data && setS(structuredClone(state.data))}>Discard</button><button className="btn-primary" disabled={!!wErr}>Save settings</button></div>
      </div>
    </form>
  );
}

function PoliciesTab() {
  const state = useApi<Policy[]>("/api/admin/policies");
  return <Async state={state}>{(ps) => <div className="grid gap-6 2xl:grid-cols-3 xl:grid-cols-2">{ps.map((p) => <PolicyForm key={p.id} policy={p} onSaved={state.reload} />)}</div>}</Async>;
}

function PolicyForm({ policy, onSaved }: { policy: Policy; onSaved: () => void }) {
  const [p, setP] = useState<Policy>(structuredClone(policy));
  const act = useAction();
  const errs = slabErrors(p.fine_slabs);
  const setSlab = (i: number, patch: Partial<Slab>) => setP({ ...p, fine_slabs: p.fine_slabs.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  async function save(e: FormEvent) {
    e.preventDefault();
    if (errs.length) return;
    const { id: _id, member_type: _mt, ...body } = p;
    void _id; void _mt;
    const r = await act(() => put(`/api/admin/policies/${policy.member_type}`, body), `${p.label} policy saved`);
    if (r) onSaved();
  }
  const num = (k: keyof Policy, label: string) => (
    <Field label={label} htmlFor={`${policy.member_type}-${k}`}><input id={`${policy.member_type}-${k}`} type="number" min={0} className="input" value={p[k] as number} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} /></Field>
  );
  return (
    <Card title={`${p.label} policy`}>
      <form onSubmit={save} className="space-y-4" noValidate>
        <div className="grid grid-cols-2 gap-3">
          {num("max_loans", "Max loans")}{num("loan_days", "Loan days")}{num("max_renewals", "Max renewals")}{num("max_reservations", "Max reservations")}
          {num("grace_days", "Grace days")}{num("max_fine", "Fine cap (₹)")}{num("lost_after_days", "Lost after (days)")}{num("lost_processing_fee", "Lost fee (₹)")}{num("hold_days", "Hold days")}
          <label className="mt-6 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-[rgb(var(--accent))]" checked={p.exclude_sundays} onChange={(e) => setP({ ...p, exclude_sundays: e.target.checked })} />Sundays free</label>
        </div>
        <div>
          <p className="label">Fine slabs (per chargeable day)</p>
          <ul className="space-y-2">
            {p.fine_slabs.map((s, i) => (
              <li key={i} className="grid grid-cols-[1fr,1fr,1fr,auto] items-center gap-2 text-sm">
                <label><span className="sr-only">From day</span><input type="number" min={1} className="input" value={s.from_day} onChange={(e) => setSlab(i, { from_day: Number(e.target.value) })} /></label>
                <label><span className="sr-only">To day</span><input type="number" min={1} className="input" placeholder="open" value={s.to_day ?? ""} onChange={(e) => setSlab(i, { to_day: e.target.value === "" ? null : Number(e.target.value) })} /></label>
                <label><span className="sr-only">Rate</span><input type="number" min={0} step={0.5} className="input" value={s.rate} onChange={(e) => setSlab(i, { rate: Number(e.target.value) })} /></label>
                <button type="button" className="btn-ghost px-2" disabled={p.fine_slabs.length <= 1} onClick={() => setP({ ...p, fine_slabs: p.fine_slabs.filter((_, j) => j !== i) })} aria-label={`Remove slab ${i + 1}`}><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">From day · to day (blank = open-ended) · ₹ per day</p>
          {p.fine_slabs.length < 6 && <button type="button" className="btn-ghost mt-1 text-xs" onClick={() => {
            const last = p.fine_slabs[p.fine_slabs.length - 1];
            const end = last.from_day + 6;
            setP({ ...p, fine_slabs: [...p.fine_slabs.slice(0, -1), { ...last, to_day: end }, { from_day: end + 1, to_day: null, rate: last.rate * 2 }] });
          }}><Plus className="h-3.5 w-3.5" aria-hidden />Add slab</button>}
          {errs.length > 0 && <Notice tone="error"><ul className="list-disc pl-4">{errs.map((e) => <li key={e}>{e}</li>)}</ul></Notice>}
        </div>
        <button className="btn-primary w-full" disabled={errs.length > 0}>Save {p.label.toLowerCase()} policy</button>
      </form>
    </Card>
  );
}

function HolidaysTab() {
  const state = useApi<{ id: number; date: string; name: string }[]>("/api/admin/holidays");
  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const act = useAction();
  async function add(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!date || name.trim().length < 2) return;
    const r = await act(() => post("/api/admin/holidays", { date, name }), "Holiday added — it is excluded from all fines");
    if (r) { setDate(""); setName(""); setTouched(false); state.reload(); }
  }
  async function remove(id: number) {
    const r = await act(() => del(`/api/admin/holidays/${id}`).then(() => true), "Holiday removed");
    if (r) state.reload();
  }
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr,2fr]">
      <Card title="Add a holiday" subtitle="Holidays are never charged and push due dates to the next open day">
        <form onSubmit={add} className="space-y-3" noValidate>
          <Field label="Date" htmlFor="h-date" error={touched && !date ? "Choose a date" : null}><input id="h-date" type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="Name" htmlFor="h-name" error={touched && name.trim().length < 2 ? "Enter a name" : null}><input id="h-name" className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></Field>
          <button className="btn-primary w-full">Add holiday</button>
        </form>
      </Card>
      <Card title="Library holidays">
        <Async state={state}>{(hs) => (
          <ul className="divide-y divide-line">{hs.map((h) => (
            <li key={h.id} className="flex items-center justify-between gap-2 py-2 text-sm"><span><span className="mr-3 font-mono text-xs">{fmtDate(h.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</span>{h.name}</span>
              <button className="btn-ghost px-2" onClick={() => remove(h.id)} aria-label={`Remove ${h.name}`}><Trash2 className="h-4 w-4" /></button></li>
          ))}</ul>
        )}</Async>
      </Card>
    </div>
  );
}

function UsersTab() {
  const me = useUser();
  const state = useApi<User[]>("/api/admin/users");
  const [f, setF] = useState({ email: "", name: "", role: "librarian", password: "" });
  const [touched, setTouched] = useState(false);
  const act = useAction();
  const errors = { email: isEmail(f.email) ? null : "Valid email required", name: f.name.trim().length >= 2 ? null : "Name required",
    password: f.password.length >= 8 && /\d/.test(f.password) && /[a-z]/i.test(f.password) ? null : "8+ characters with letters and digits" };
  async function create(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.values(errors).some(Boolean)) return;
    const r = await act(() => post("/api/admin/users", f), "Staff account created");
    if (r) { setF({ email: "", name: "", role: "librarian", password: "" }); setTouched(false); state.reload(); }
  }
  async function toggle(u: User) {
    const r = await act(() => put(`/api/admin/users/${u.id}`, { is_active: !u.is_active }), u.is_active ? "Account disabled" : "Account enabled");
    if (r) state.reload();
  }
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr,2fr]">
      <Card title="New staff account">
        <form onSubmit={create} className="space-y-3" noValidate>
          <Field label="Name" htmlFor="u-name" error={touched ? errors.name : null}><input id="u-name" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Email" htmlFor="u-email" error={touched ? errors.email : null}><input id="u-email" type="email" className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Role" htmlFor="u-role"><select id="u-role" className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="librarian">Librarian</option><option value="admin">Admin</option></select></Field>
          <Field label="Password" htmlFor="u-pw" error={touched ? errors.password : null}><input id="u-pw" type="password" className="input" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
          <p className="text-xs text-muted">Passwords are stored as salted PBKDF2-SHA256 hashes. Member accounts are created from the Members page.</p>
          <button className="btn-primary w-full">Create account</button>
        </form>
      </Card>
      <Card title="Accounts">
        <Async state={state}>{(users) => (
          <TableWrap label="Users"><table className="table-base"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th className="text-right"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{users.map((u) => (
              <tr key={u.id}><td>{u.name}</td><td className="font-mono text-xs">{u.email}</td><td>{humanise(u.role)}</td><td><StatusBadge status={u.is_active ? "active" : "suspended"} label={u.is_active ? "active" : "disabled"} /></td>
                <td className="text-right">{u.id !== me.id && <button className="btn-ghost px-2 py-1 text-xs" onClick={() => toggle(u)}>{u.is_active ? "Disable" : "Enable"}</button>}</td></tr>
            ))}</tbody></table></TableWrap>
        )}</Async>
      </Card>
    </div>
  );
}
