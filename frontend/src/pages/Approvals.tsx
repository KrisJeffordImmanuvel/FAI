import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Check, ShieldCheck, User, X } from "lucide-react";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { post, qs } from "../lib/api";
import { fmtDate, humanise, rupees } from "../lib/format";
import type { Approval } from "../lib/types";
import { Async, Card, EmptyState, Field, Modal, PageHeader, StatusBadge, Tabs } from "../components/ui";
import { RuleTrace } from "../components/explain";
import { useAction } from "../components/toast";

const KIND = { waiver: "Fine waiver", restrict_member: "Restrict borrowing", mark_lost: "Mark book as lost" } as Record<string, string>;

export default function Approvals() {
  const { tick, bump } = useAgent();
  const [status, setStatus] = useState<"pending" | "approved" | "rejected" | "withdrawn" | "all">("pending");
  const state = useApi<{ items: Approval[] }>(`/api/approvals${qs({ status })}`, [tick]);
  const [deciding, setDeciding] = useState<{ a: Approval; approve: boolean } | null>(null);
  return (
    <div>
      <PageHeader eyebrow="Human oversight" title="Approvals"
        description="High-impact actions — waivers, membership restrictions and marking books lost — are only ever recommended by the agent or requested by people. A librarian decides." />
      <div className="mb-4"><Tabs label="Approval status" value={status} onChange={setStatus} options={[
        { value: "pending", label: "Pending" }, { value: "approved", label: "Approved" }, { value: "rejected", label: "Rejected" }, { value: "withdrawn", label: "Withdrawn" }, { value: "all", label: "All" }]} /></div>
      <Async state={state} isEmpty={(d) => d.items.length === 0} empty={<EmptyState title="Nothing waiting for a decision" icon={<ShieldCheck className="h-6 w-6" />}>New recommendations appear after agent cycles.</EmptyState>}>
        {(d) => (
          <div className="grid gap-4 xl:grid-cols-2">
            {d.items.map((a) => (
              <Card key={a.id} title={KIND[a.kind] ?? humanise(a.kind)} subtitle={`#${a.id} · ${fmtDate(a.created_on)}`}
                actions={<span className="flex items-center gap-1.5 text-xs text-ink2">{a.source === "agent" ? <Bot className="h-3.5 w-3.5" aria-hidden /> : <User className="h-3.5 w-3.5" aria-hidden />}{a.requested_by}<StatusBadge status={a.status} /></span>}>
                <div className="space-y-3 text-sm">
                  {a.member_id && <p>Member: <Link className="font-medium underline" to={`/members/${a.member_id}`}>{a.member_name}</Link>{a.loan_id && <span className="text-muted"> · loan #{a.loan_id}</span>}
                    {typeof a.payload.amount === "number" && <span className="text-muted"> · amount {rupees(a.payload.amount as number)}</span>}</p>}
                  <p className="rounded-lg bg-sunken/70 p-2">{a.reason}</p>
                  {a.explanation?.rules && a.explanation.rules.length > 0 && (
                    <details><summary className="cursor-pointer text-xs font-medium text-ink2">Why the agent recommends this ({a.explanation.rules.length} rule firings)</summary>
                      <div className="mt-2"><RuleTrace firings={a.explanation.rules} compact /></div>
                      {a.explanation.note && <p className="mt-2 text-xs text-muted">{a.explanation.note}</p>}
                    </details>
                  )}
                  {a.decision_note && <p className="text-xs text-muted">Decision note: {a.decision_note} ({fmtDate(a.decided_on)})</p>}
                  {a.status === "pending" && (
                    <div className="flex justify-end gap-2">
                      <button className="btn-secondary" onClick={() => setDeciding({ a, approve: false })}><X className="h-4 w-4" aria-hidden />Reject</button>
                      <button className="btn-primary" onClick={() => setDeciding({ a, approve: true })}><Check className="h-4 w-4" aria-hidden />Approve</button>
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </Async>
      {deciding && <DecideModal {...deciding} onClose={() => setDeciding(null)} onDone={() => { state.reload(); bump(); }} />}
    </div>
  );
}

function DecideModal({ a, approve, onClose, onDone }: { a: Approval; approve: boolean; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [touched, setTouched] = useState(false);
  const act = useAction();
  const needs = !approve ? 3 : a.kind === "waiver" ? 0 : 0;
  const error = note.trim().length < needs ? "Please record why (at least 3 characters)" : null;
  async function submit() {
    setTouched(true);
    if (error) return;
    const r = await act(() => post(`/api/approvals/${a.id}/decide`, { approve, note }), approve ? "Approved and executed" : "Rejected — the agent will not re-suggest this for 7 days");
    if (r) { onDone(); onClose(); }
  }
  return (
    <Modal open onClose={onClose} title={`${approve ? "Approve" : "Reject"}: ${KIND[a.kind] ?? a.kind}`}>
      <div className="space-y-3">
        <p className="text-sm text-ink2">{approve ? (a.kind === "mark_lost" ? "The loan becomes lost and the replacement cost + processing fee are charged." :
          a.kind === "restrict_member" ? "The member will not be able to borrow or reserve until reactivated." : "The outstanding amount will be waived with this reason recorded.") : "No action will be taken."}</p>
        <Field label={approve ? "Note (optional, audited)" : "Reason for rejecting (required)"} htmlFor="dn" error={touched ? error : null}>
          <textarea id="dn" rows={3} className="input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} /></Field>
        <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button><button className={approve ? "btn-primary" : "btn-danger"} onClick={submit}>{approve ? "Approve" : "Reject"}</button></div>
      </div>
    </Modal>
  );
}
