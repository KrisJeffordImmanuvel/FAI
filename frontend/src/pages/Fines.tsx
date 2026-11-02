import { useState, type FormEvent } from "react";
import { Calculator, HandCoins } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { post, qs } from "../lib/api";
import { fmtDate, humanise, rupees } from "../lib/format";
import type { FineBreakdown, FineDetail, Fine, Page } from "../lib/types";
import { can } from "../lib/roles";
import { amountError } from "../lib/validation";
import { Async, Card, EmptyState, Field, Modal, Notice, PageHeader, Pagination, StatusBadge, TableWrap, Tabs } from "../components/ui";
import { FineStatement } from "../components/explain";
import { useAction } from "../components/toast";

type Status = "unpaid" | "paid" | "waived" | "all";

export default function Fines() {
  const user = useUser();
  const { tick } = useAgent();
  const [status, setStatus] = useState<Status>("unpaid");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const state = useApi<Page<Fine>>(`/api/fines${qs({ status, page, page_size: 25 })}`, [tick]);
  const staff = can.manageCirculation(user.role);
  return (
    <div>
      <PageHeader eyebrow="Accounts" title="Fines" description="Every fine is calculated deterministically from slab rates, grace periods, holidays, Sundays and caps — with a day-by-day statement." />
      <div className="grid gap-6 2xl:grid-cols-[1.6fr,1fr]">
        <div className="card p-4">
          <div className="mb-3"><Tabs label="Fine status" value={status} onChange={(s) => { setStatus(s); setPage(1); }} options={[
            { value: "unpaid", label: "Outstanding" }, { value: "paid", label: "Paid" }, { value: "waived", label: "Waived" }, { value: "all", label: "All" }]} /></div>
          <Async state={state} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="No fines in this view" />}>
            {(p) => (
              <>
                <TableWrap label="Fines">
                  <table className="table-base">
                    <thead><tr>{staff && <th>Member</th>}<th>Title</th><th>Kind</th><th>Assessed</th><th>Balance</th><th>Status</th><th className="text-right"><span className="sr-only">Open</span></th></tr></thead>
                    <tbody>{p.items.map((f) => (
                      <tr key={f.id}>
                        {staff && <td>{f.member_name}<p className="font-mono text-xs text-muted">{f.member_code}</p></td>}
                        <td><p className="font-medium">{f.title}</p><p className="text-xs text-muted">due {fmtDate(f.due_on)}{f.returned_on ? ` · returned ${fmtDate(f.returned_on)}` : " · still out"}</p></td>
                        <td>{humanise(f.kind)}</td>
                        <td className="num font-mono text-xs">{rupees(f.amount)}</td>
                        <td className="num font-mono text-xs font-medium">{rupees(f.balance)}</td>
                        <td><StatusBadge status={f.status} /></td>
                        <td className="text-right"><button className="btn-secondary px-2.5 py-1 text-xs" onClick={() => setOpen(f.id)}>Statement</button></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </TableWrap>
                <Pagination page={p.page} pageSize={p.page_size} total={p.total} onPage={setPage} />
              </>
            )}
          </Async>
        </div>
        <FineCalculator />
      </div>
      {open !== null && <FineModal id={open} onClose={() => setOpen(null)} onChanged={state.reload} />}
    </div>
  );
}

function FineModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const user = useUser();
  const state = useApi<FineDetail>(`/api/fines/${id}`);
  const act = useAction();
  const staff = can.manageCirculation(user.role);
  const [mode, setMode] = useState<"pay" | "waive" | "request" | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);

  async function submit(e: FormEvent, f: FineDetail) {
    e.preventDefault();
    setTouched(true);
    if (mode !== "request" && amountError(amount, f.balance)) return;
    if (mode !== "pay" && reason.trim().length < (mode === "request" ? 10 : 5)) return;
    const call = mode === "pay" ? () => post(`/api/fines/${id}/payments`, { amount: +amount, method })
      : mode === "waive" ? () => post(`/api/fines/${id}/waive`, { amount: +amount, reason })
      : () => post(`/api/fines/${id}/waiver-request`, { reason });
    const msg = mode === "pay" ? "Payment recorded" : mode === "waive" ? "Waiver recorded with reason" : "Waiver request sent to a librarian";
    const r = await act(call, msg);
    if (r) { setMode(null); setAmount(""); setReason(""); setTouched(false); state.reload(); onChanged(); }
  }

  return (
    <Modal open onClose={onClose} title={`Fine statement #${id}`} wide>
      <Async state={state}>
        {(f) => (
          <div className="space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h3 className="font-display text-xl font-semibold">{f.title}</h3><p className="text-sm text-ink2">{f.member_name} · {humanise(f.kind)} fine</p></div>
              <div className="grid grid-cols-3 gap-3 text-center text-sm">
                <div><p className="eyebrow">Assessed</p><p className="num font-mono">{rupees(f.amount)}</p></div>
                <div><p className="eyebrow">Paid / waived</p><p className="num font-mono">{rupees(f.amount_paid + f.amount_waived)}</p></div>
                <div><p className="eyebrow">Balance</p><p className="num font-mono font-semibold text-accent">{rupees(f.balance)}</p></div>
              </div>
            </div>
            {f.status === "accruing" && <Notice tone="warn">The book is still out, so this fine is still accruing. Partial payments are accepted.</Notice>}
            <FineStatement breakdown={f.breakdown} />
            {(f.payments.length > 0 || f.waivers.length > 0) && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div><p className="label">Payments</p>{f.payments.length === 0 ? <p className="text-sm text-muted">None</p> : (
                  <ul className="space-y-1 text-sm">{f.payments.map((p) => <li key={p.id} className="flex justify-between"><span>{fmtDate(p.paid_on)} · {p.method.toUpperCase()}</span><span className="font-mono">{rupees(p.amount)}</span></li>)}</ul>)}</div>
                <div><p className="label">Waivers</p>{f.waivers.length === 0 ? <p className="text-sm text-muted">None</p> : (
                  <ul className="space-y-1 text-sm">{f.waivers.map((w) => <li key={w.id}><span className="flex justify-between"><span>{fmtDate(w.waived_on)}</span><span className="font-mono">{rupees(w.amount)}</span></span><span className="text-xs text-muted">{w.reason}</span></li>)}</ul>)}</div>
              </div>
            )}
            {f.balance > 0 && (
              <div className="rounded-lg border border-line p-3">
                <div className="flex flex-wrap gap-2">
                  {staff && <button className={mode === "pay" ? "btn-primary" : "btn-secondary"} onClick={() => { setMode("pay"); setAmount(String(f.balance)); }}><HandCoins className="h-4 w-4" aria-hidden />Record payment</button>}
                  {staff && <button className={mode === "waive" ? "btn-primary" : "btn-secondary"} onClick={() => { setMode("waive"); setAmount(String(f.balance)); }}>Waive</button>}
                  {!staff && <button className={mode === "request" ? "btn-primary" : "btn-secondary"} onClick={() => setMode("request")}>Request a review / waiver</button>}
                  {!staff && <p className="self-center text-xs text-muted">Payments are made at the circulation desk (full or partial).</p>}
                </div>
                {mode && (
                  <form onSubmit={(e) => submit(e, f)} className="mt-3 grid gap-3 sm:grid-cols-2" noValidate>
                    {mode !== "request" && <Field label="Amount (₹)" htmlFor="amt" error={touched ? amountError(amount, f.balance) : null} hint={`Balance ${rupees(f.balance)} — partial amounts allowed`}>
                      <input id="amt" className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>}
                    {mode === "pay" && <Field label="Method" htmlFor="mth"><select id="mth" className="input" value={method} onChange={(e) => setMethod(e.target.value)}><option value="cash">Cash</option><option value="upi">UPI</option><option value="card">Card</option></select></Field>}
                    {mode !== "pay" && <div className="sm:col-span-2"><Field label={mode === "waive" ? "Reason (required, audited)" : "Why should this fine be reviewed?"} htmlFor="rsn"
                      error={touched && reason.trim().length < (mode === "request" ? 10 : 5) ? `At least ${mode === "request" ? 10 : 5} characters` : null}>
                      <textarea id="rsn" rows={2} className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} /></Field></div>}
                    <div className="flex justify-end gap-2 sm:col-span-2"><button type="button" className="btn-secondary" onClick={() => setMode(null)}>Cancel</button><button className="btn-primary">Confirm</button></div>
                  </form>
                )}
              </div>
            )}
          </div>
        )}
      </Async>
    </Modal>
  );
}

function FineCalculator() {
  const [f, setF] = useState({ member_type: "student", due_on: "2026-11-02", returned_on: "2026-11-25", lost: false, replacement_cost: "650" });
  const [result, setResult] = useState<FineBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const act = useAction();
  async function run(e: FormEvent) {
    e.preventDefault();
    if (!f.due_on || !f.returned_on) { setError("Choose both dates"); return; }
    setError(null);
    const r = await act(() => post<FineBreakdown>("/api/fines/preview", { ...f, replacement_cost: +f.replacement_cost || 0 }));
    if (r) setResult(r);
  }
  return (
    <Card title={<span className="flex items-center gap-2"><Calculator className="h-4 w-4 text-accent" aria-hidden />Fine calculator</span>} subtitle="Runs the same engine against current policies and holidays — nothing is saved">
      <form onSubmit={run} className="grid gap-3 sm:grid-cols-2" noValidate>
        <Field label="Member type" htmlFor="c-type"><select id="c-type" className="input" value={f.member_type} onChange={(e) => setF({ ...f, member_type: e.target.value })}>
          <option value="student">Student</option><option value="faculty">Faculty</option><option value="staff">Staff</option></select></Field>
        <label className="mt-6 flex items-center gap-2 text-sm"><input type="checkbox" checked={f.lost} onChange={(e) => setF({ ...f, lost: e.target.checked })} className="h-4 w-4 accent-[rgb(var(--accent))]" />Declared lost</label>
        <Field label="Due date" htmlFor="c-due"><input id="c-due" type="date" className="input" value={f.due_on} onChange={(e) => setF({ ...f, due_on: e.target.value })} /></Field>
        <Field label={f.lost ? "Declared lost on" : "Returned on"} htmlFor="c-ret"><input id="c-ret" type="date" className="input" value={f.returned_on} onChange={(e) => setF({ ...f, returned_on: e.target.value })} /></Field>
        {f.lost && <Field label="Replacement cost (₹)" htmlFor="c-cost"><input id="c-cost" className="input" inputMode="decimal" value={f.replacement_cost} onChange={(e) => setF({ ...f, replacement_cost: e.target.value })} /></Field>}
        {error && <p className="text-sm text-crit sm:col-span-2">{error}</p>}
        <div className="sm:col-span-2"><button className="btn-primary w-full">Calculate</button></div>
      </form>
      {result && <div className="mt-4 border-t border-line pt-4"><FineStatement breakdown={result} /></div>}
    </Card>
  );
}
