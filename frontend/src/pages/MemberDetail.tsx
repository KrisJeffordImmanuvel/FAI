import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useApi } from "../lib/useApi";
import { post } from "../lib/api";
import { dueText, fmtDate, humanise, pct, rupees, CHANNEL_LABELS } from "../lib/format";
import type { MemberDetail as MD } from "../lib/types";
import { Async, Card, EmptyState, Field, KeyValue, Kpi, Modal, PageHeader, RiskPill, StatusBadge, TableWrap } from "../components/ui";
import { useAction } from "../components/toast";

export default function MemberDetail() {
  const { id } = useParams();
  const state = useApi<MD>(`/api/members/${id}`);
  const [statusModal, setStatusModal] = useState(false);
  return (
    <div>
      <Link to="/members" className="btn-ghost mb-3 px-2"><ArrowLeft className="h-4 w-4" aria-hidden />All members</Link>
      <Async state={state}>
        {(m) => (
          <>
            <PageHeader eyebrow={`${humanise(m.member_type)} · ${m.code}`} title={m.name} description={`${m.department} · joined ${fmtDate(m.joined_on)}`}
              actions={<><StatusBadge status={m.status} /><button className="btn-secondary" onClick={() => setStatusModal(true)}>Change status</button></>} />
            {m.restriction_reason && <p className="mb-4 rounded-lg border border-crit/30 bg-crit/5 px-3 py-2 text-sm">Reason: {m.restriction_reason}</p>}
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
              <Kpi label="Active loans" value={`${m.stats.active_loans}/${m.policy.max_loans}`} />
              <Kpi label="Overdue" value={m.stats.overdue_loans} tone={m.stats.overdue_loans ? "crit" : "ink"} />
              <Kpi label="Past loans" value={m.stats.prior_loans} hint={`${m.stats.late_loans} returned late`} />
              <Kpi label="Late rate" value={pct(m.stats.late_rate)} hint="Used as a member-history factor" />
              <Kpi label="Unpaid fines" value={rupees(m.stats.unpaid_fines)} tone="accent" />
            </div>
            <div className="grid gap-6 xl:grid-cols-[2fr,1fr]">
              <Card title="Active loans">
                {m.active_loans.length === 0 ? <EmptyState title="No active loans" /> : (
                  <TableWrap label="Active loans"><table className="table-base">
                    <thead><tr><th>Title</th><th>Issued</th><th>Due</th><th>Risk (advisory)</th><th>Fine</th></tr></thead>
                    <tbody>{m.active_loans.map((l) => (
                      <tr key={l.id}><td><p className="font-medium">{l.title}</p><p className="font-mono text-xs text-muted">{l.barcode}</p></td>
                        <td className="whitespace-nowrap">{fmtDate(l.issued_on)}</td>
                        <td className="whitespace-nowrap">{fmtDate(l.due_on)}<p className={(l.days_until_due ?? 0) < 0 ? "text-xs text-crit" : "text-xs text-muted"}>{dueText(l.days_until_due)}</p></td>
                        <td><RiskPill score={l.risk_score} label={l.risk_label} /></td>
                        <td className="num font-mono text-xs">{l.fine_amount ? rupees(l.fine_amount) : "—"}</td></tr>
                    ))}</tbody></table></TableWrap>
                )}
              </Card>
              <Card title="Profile & policy">
                <KeyValue items={[["Email", m.email], ["Phone", m.phone], ["Notifications", CHANNEL_LABELS[m.notify_pref]], ["Policy", m.policy.label],
                  ["Loan period", `${m.policy.loan_days} days`], ["Renewals", m.policy.max_renewals], ["Reservations", m.policy.max_reservations],
                  ["Grace period", `${m.policy.grace_days} days`], ["Fine cap", rupees(m.policy.max_fine)]]} />
              </Card>
              <Card title="Fines" className="xl:col-span-2">
                {m.fines.length === 0 ? <EmptyState title="No fines — great borrowing record" /> : (
                  <TableWrap label="Fines"><table className="table-base"><thead><tr><th>Title</th><th>Kind</th><th>Assessed</th><th>Paid</th><th>Waived</th><th>Balance</th><th>Status</th></tr></thead>
                    <tbody>{m.fines.map((f) => (
                      <tr key={f.id}><td>{f.title}</td><td>{humanise(f.kind)}</td><td className="num font-mono text-xs">{rupees(f.amount)}</td><td className="num font-mono text-xs">{rupees(f.amount_paid)}</td>
                        <td className="num font-mono text-xs">{rupees(f.amount_waived)}</td><td className="num font-mono text-xs font-medium">{rupees(f.balance)}</td><td><StatusBadge status={f.status} /></td></tr>
                    ))}</tbody></table></TableWrap>
                )}
              </Card>
              <Card title="Reservations">
                {m.reservations.length === 0 ? <EmptyState title="No reservations" /> : (
                  <ul className="divide-y divide-line text-sm">{m.reservations.map((r) => (
                    <li key={r.id} className="flex items-center justify-between gap-2 py-2"><span className="min-w-0 truncate">{r.title}</span><StatusBadge status={r.status} label={r.position ? `#${r.position} waiting` : undefined} /></li>
                  ))}</ul>
                )}
              </Card>
              <Card title="Circulation history" className="xl:col-span-3">
                {m.history.length === 0 ? <EmptyState title="No past loans" /> : (
                  <TableWrap label="History"><table className="table-base"><thead><tr><th>Title</th><th>Issued</th><th>Due</th><th>Returned</th><th>Outcome</th></tr></thead>
                    <tbody>{m.history.map((l) => (
                      <tr key={l.id}><td>{l.title}</td><td>{fmtDate(l.issued_on)}</td><td>{fmtDate(l.due_on)}</td><td>{fmtDate(l.returned_on)}</td>
                        <td>{l.status === "lost" ? <StatusBadge status="lost" /> : l.days_late ? <span className="text-xs text-crit">{l.days_late} day(s) late</span> : <span className="text-xs text-good">On time</span>}</td></tr>
                    ))}</tbody></table></TableWrap>
                )}
              </Card>
            </div>
            <StatusModal open={statusModal} onClose={() => setStatusModal(false)} member={m} onSaved={state.reload} />
          </>
        )}
      </Async>
    </div>
  );
}

function StatusModal({ open, onClose, member, onSaved }: { open: boolean; onClose: () => void; member: MD; onSaved: () => void }) {
  const [status, setStatus] = useState(member.status);
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const act = useAction();
  const error = status !== "active" && reason.trim().length < 5 ? "A reason (at least 5 characters) is required — this is a high-impact decision" : null;
  async function save() {
    setTouched(true);
    if (error) return;
    const r = await act(() => post(`/api/members/${member.id}/status`, { status, reason }), "Membership status updated and audited");
    if (r) { onSaved(); onClose(); }
  }
  return (
    <Modal open={open} onClose={onClose} title={`Change status · ${member.name}`}>
      <div className="space-y-3">
        <Field label="Status" htmlFor="st"><select id="st" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="active">Active</option><option value="restricted">Restricted (no new loans/reservations)</option><option value="suspended">Suspended</option></select></Field>
        <Field label="Reason (recorded in the audit log)" htmlFor="rs" error={touched ? error : null}><textarea id="rs" rows={3} className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255} /></Field>
        <p className="text-xs text-muted">The agent can only <em>suggest</em> restrictions (based on recorded fines and overdue loans, never on predictions). A librarian makes the decision here or in Approvals.</p>
        <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save}>Save</button></div>
      </div>
    </Modal>
  );
}
