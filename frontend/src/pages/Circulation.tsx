import { useEffect, useState, type FormEvent } from "react";
import { BookCheck, RotateCcw, ScanBarcode, Search, TriangleAlert } from "lucide-react";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { post, qs } from "../lib/api";
import { dueText, fmtDate, rupees } from "../lib/format";
import type { FineDetail, Loan, Member, Page } from "../lib/types";
import { Async, Card, EmptyState, Field, Modal, Notice, PageHeader, Pagination, RiskPill, StatusBadge, TableWrap, Tabs, cx } from "../components/ui";
import { useAction } from "../components/toast";
import LoanDetailModal from "../components/LoanDetail";

type Tab = "active" | "overdue" | "returned" | "lost" | "all";

export default function Circulation() {
  const { tick, bump } = useAgent();
  const [tab, setTab] = useState<Tab>("active");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<number | null>(null);
  const [lostFor, setLostFor] = useState<Loan | null>(null);
  const [lastReturn, setLastReturn] = useState<{ loan: Loan; fine: FineDetail | null; allocation: { member_name: string; expires_on: string } | null } | null>(null);
  useEffect(() => setPage(1), [tab, q]);
  const loans = useApi<Page<Loan>>(`/api/loans${qs({ status: tab, q, page, page_size: 25 })}`, [tick]);
  const act = useAction();

  async function doReturn(l: Loan) {
    const r = await act(() => post<{ loan: Loan; fine: FineDetail | null; allocation: { member_name: string; expires_on: string } | null }>(`/api/loans/${l.id}/return`), "Return processed");
    if (r) { setLastReturn(r); loans.reload(); bump(); }
  }
  async function renew(l: Loan) {
    const r = await act(() => post<Loan>(`/api/loans/${l.id}/renew`), (x) => `Renewed — now due ${fmtDate(x.due_on)}`);
    if (r) loans.reload();
  }

  return (
    <div>
      <PageHeader eyebrow="Desk" title="Circulation" description="Issue, return and renew. Returns are fined deterministically and automatically allocate the copy to the reservation queue." />
      <div className="mb-6 grid gap-6 xl:grid-cols-[1fr,1fr]">
        <IssueDesk onIssued={() => { loans.reload(); bump(); }} />
        <Card title="Last return" subtitle="Fine statement and queue allocation">
          {!lastReturn ? <EmptyState title="No return processed in this session" icon={<RotateCcw className="h-6 w-6" />}>Use “Return” on a loan below.</EmptyState> : (
            <div className="space-y-2 text-sm">
              <p><strong>{lastReturn.loan.title}</strong> returned by {lastReturn.loan.member_name}.</p>
              {lastReturn.fine ? <Notice tone="warn">Fine {rupees(lastReturn.fine.amount)} — {lastReturn.fine.summary}</Notice> : <Notice tone="success">Returned on time — no fine.</Notice>}
              {lastReturn.allocation ? <Notice tone="info">Copy put on hold for <strong>{lastReturn.allocation.member_name}</strong> (first in queue) until {fmtDate(lastReturn.allocation.expires_on)}. A notification was dispatched.</Notice>
                : <p className="text-muted">Nobody was waiting — the copy is back on the shelf.</p>}
            </div>
          )}
        </Card>
      </div>
      <div className="card p-4">
        <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <Tabs label="Loan filter" value={tab} onChange={setTab} options={[
            { value: "active", label: "Active" }, { value: "overdue", label: "Overdue" }, { value: "returned", label: "Returned" }, { value: "lost", label: "Lost" }, { value: "all", label: "All history" }]} />
          <label className="relative lg:w-80"><span className="sr-only">Search loans</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input className="input pl-9" placeholder="Title, member, code, barcode…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} />
          </label>
        </div>
        <Async state={loans} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="No loans in this view" />}>
          {(p) => (
            <>
              <TableWrap label="Loans">
                <table className="table-base">
                  <thead><tr><th>Title / copy</th><th>Member</th><th>Issued</th><th>Due</th><th>Risk (advisory)</th><th>Fine</th><th className="text-right">Actions</th></tr></thead>
                  <tbody>
                    {p.items.map((l) => (
                      <tr key={l.id}>
                        <td><button className="text-left font-medium hover:text-accent hover:underline" onClick={() => setDetail(l.id)}>{l.title}</button><p className="font-mono text-xs text-muted">{l.barcode}</p></td>
                        <td>{l.member_name}<p className="font-mono text-xs text-muted">{l.member_code}</p></td>
                        <td className="whitespace-nowrap text-xs">{fmtDate(l.issued_on)}</td>
                        <td className="whitespace-nowrap text-xs">{fmtDate(l.due_on)}
                          {l.status === "active" ? <p className={cx((l.days_until_due ?? 0) < 0 ? "text-crit" : "text-muted")}>{dueText(l.days_until_due)}</p>
                            : <p className="text-muted">{l.status === "returned" ? (l.days_late ? `returned ${l.days_late}d late` : "returned on time") : l.status}</p>}</td>
                        <td><RiskPill score={l.risk_score} label={l.risk_label} /></td>
                        <td className="num font-mono text-xs">{l.fine_amount ? <>{rupees(l.fine_amount)}{l.fine_balance > 0 && <p className="text-muted">bal {rupees(l.fine_balance)}</p>}</> : "—"}</td>
                        <td className="text-right">
                          {l.status === "active" ? (
                            <div className="flex justify-end gap-1">
                              <button className="btn-primary px-2.5 py-1 text-xs" onClick={() => doReturn(l)}>Return</button>
                              <button className="btn-secondary px-2.5 py-1 text-xs" onClick={() => renew(l)} disabled={(l.days_until_due ?? 0) < 0}>Renew</button>
                              {(l.days_overdue ?? 0) > 0 && <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setLostFor(l)} title="Report lost (needs approval)"><TriangleAlert className="h-3.5 w-3.5" aria-hidden /><span className="sr-only">Report lost</span></button>}
                            </div>
                          ) : <StatusBadge status={l.status} />}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
              <Pagination page={p.page} pageSize={p.page_size} total={p.total} onPage={setPage} />
            </>
          )}
        </Async>
      </div>
      {detail !== null && <LoanDetailModal id={detail} onClose={() => setDetail(null)} />}
      {lostFor && <LostModal loan={lostFor} onClose={() => setLostFor(null)} />}
    </div>
  );
}

function IssueDesk({ onIssued }: { onIssued: () => void }) {
  const [memberQ, setMemberQ] = useState("");
  const [member, setMember] = useState<Member | null>(null);
  const [barcode, setBarcode] = useState("");
  const [touched, setTouched] = useState(false);
  const [result, setResult] = useState<Loan | null>(null);
  const members = useApi<Page<Member>>(!member && memberQ.length >= 2 ? `/api/members${qs({ q: memberQ, page_size: 6 })}` : null);
  const act = useAction();
  const errors = { member: member ? null : "Choose a member", barcode: /^[A-Za-z0-9-]{3,30}$/.test(barcode.trim()) ? null : "Scan or type a copy barcode (e.g. LIB-00012)" };
  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (errors.member || errors.barcode || !member) return;
    const r = await act(() => post<Loan>("/api/loans/issue", { member_id: member.id, barcode: barcode.trim().toUpperCase() }), (l) => `Issued “${l.title}” — due ${fmtDate(l.due_on)}`);
    if (r) { setResult(r); setBarcode(""); setTouched(false); onIssued(); }
  }
  return (
    <Card title="Issue desk" subtitle="Checks limits, holds and restrictions; predicts late-return risk at checkout">
      <form onSubmit={submit} className="space-y-3" noValidate>
        <Field label="Member" htmlFor="iss-member" error={touched ? errors.member : null}>
          <input id="iss-member" className="input" placeholder="Search name or code…" value={memberQ} onChange={(e) => { setMemberQ(e.target.value); setMember(null); }} autoComplete="off" />
        </Field>
        {members.data && (
          <ul className="max-h-40 overflow-y-auto rounded-lg border border-line">
            {members.data.items.map((m) => (
              <li key={m.id}><button type="button" className="w-full px-3 py-1.5 text-left text-sm hover:bg-sunken" onClick={() => { setMember(m); setMemberQ(`${m.name} (${m.code})`); }}>
                {m.name} <span className="text-muted">· {m.code} · {m.member_type}{m.status !== "active" ? ` · ${m.status}` : ""}</span></button></li>
            ))}
            {members.data.items.length === 0 && <li className="px-3 py-2 text-sm text-muted">No members found</li>}
          </ul>
        )}
        <Field label="Copy barcode" htmlFor="iss-barcode" error={touched ? errors.barcode : null}>
          <div className="relative"><ScanBarcode className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input id="iss-barcode" className="input pl-9 font-mono uppercase" placeholder="LIB-00012" value={barcode} onChange={(e) => setBarcode(e.target.value)} maxLength={30} /></div>
        </Field>
        <button className="btn-primary w-full"><BookCheck className="h-4 w-4" aria-hidden />Issue book</button>
        {result && (
          <Notice tone="success">
            <strong>{result.title}</strong> issued to {result.member_name}, due {fmtDate(result.due_on)}.
            {result.risk_detail && <span className="block text-xs">Predicted late-return risk: {Math.round(result.risk_detail.probability * 100)}% ({result.risk_detail.label}) — advisory only.</span>}
          </Notice>
        )}
      </form>
    </Card>
  );
}

function LostModal({ loan, onClose }: { loan: Loan; onClose: () => void }) {
  const [reason, setReason] = useState(`Member reports the book is lost (${loan.days_overdue} days overdue)`);
  const act = useAction();
  async function submit() {
    if (reason.trim().length < 5) return;
    const r = await act(() => post(`/api/loans/${loan.id}/lost-request`, { reason }), "Lost-book request sent to the approval queue");
    if (r) onClose();
  }
  return (
    <Modal open onClose={onClose} title="Report book as lost">
      <div className="space-y-3">
        <Notice tone="warn">Marking a book lost charges the replacement cost and a processing fee. It is a high-impact action, so it goes to the approval queue for a librarian decision.</Notice>
        <Field label="Reason" htmlFor="lost-r" error={reason.trim().length < 5 ? "At least 5 characters" : null}><textarea id="lost-r" rows={3} className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-danger" onClick={submit}>Send for approval</button></div>
      </div>
    </Modal>
  );
}
