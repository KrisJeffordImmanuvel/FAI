import { useApi } from "../lib/useApi";
import { dueText, fmtDate, humanise, rupees } from "../lib/format";
import type { Loan } from "../lib/types";
import { useUser } from "../context/AuthContext";
import { Async, KeyValue, Modal, StatusBadge } from "./ui";
import { FineStatement, PredictionFactors } from "./explain";

export default function LoanDetailModal({ id, onClose }: { id: number; onClose: () => void }) {
  const state = useApi<Loan>(`/api/loans/${id}`);
  const user = useUser();
  return (
    <Modal open onClose={onClose} title={`Loan #${id}`} wide>
      <Async state={state}>
        {(l) => (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <h3 className="font-display text-xl font-semibold">{l.title}</h3>
                <p className="text-sm text-ink2">{l.author}</p>
                <div className="mt-2"><StatusBadge status={l.status} /></div>
              </div>
              <KeyValue items={[["Member", `${l.member_name} (${l.member_code})`], ["Copy", l.barcode], ["Issued", fmtDate(l.issued_on)],
                ["Due", `${fmtDate(l.due_on)}${l.status === "active" ? ` · ${dueText(l.days_until_due)}` : ""}`], ["Returned", fmtDate(l.returned_on)], ["Renewals", l.renewals]]} />
            </div>
            {user.role !== "member" && (
              <section className="rounded-lg border border-line p-3">
                <h4 className="mb-2 font-display text-base font-semibold">Late-return prediction at checkout</h4>
                <PredictionFactors prediction={l.risk_detail} />
                {l.risk_detail?.features && (
                  <details className="mt-2 text-xs"><summary className="cursor-pointer text-ink2">Checkout-time features (no leakage, no sensitive attributes)</summary>
                    <ul className="mt-1 grid gap-x-4 sm:grid-cols-2">{Object.entries(l.risk_detail.features).map(([k, v]) => <li key={k} className="font-mono">{humanise(k)}: {String(v)}</li>)}</ul>
                  </details>
                )}
              </section>
            )}
            <section>
              <h4 className="mb-2 font-display text-base font-semibold">Fine {l.fine ? `· ${rupees(l.fine.amount)} (${humanise(l.fine.status)})` : ""}</h4>
              {l.fine ? <FineStatement breakdown={l.fine.breakdown} /> : <p className="text-sm text-muted">No fine on this loan.</p>}
            </section>
          </div>
        )}
      </Async>
    </Modal>
  );
}
