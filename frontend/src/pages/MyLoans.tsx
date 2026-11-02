import { useState } from "react";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { post, qs } from "../lib/api";
import { dueText, fmtDate, rupees } from "../lib/format";
import type { Loan, Page } from "../lib/types";
import { Async, EmptyState, PageHeader, Pagination, StatusBadge, TableWrap, Tabs, cx } from "../components/ui";
import { useAction } from "../components/toast";
import LoanDetailModal from "../components/LoanDetail";

export default function MyLoans() {
  const { tick } = useAgent();
  const [tab, setTab] = useState<"active" | "all">("active");
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<number | null>(null);
  const loans = useApi<Page<Loan>>(`/api/loans${qs({ status: tab, page, page_size: 20 })}`, [tick]);
  const act = useAction();
  async function renew(id: number) {
    const r = await act(() => post<Loan>(`/api/loans/${id}/renew`), (l) => `Renewed — now due ${fmtDate(l.due_on)}`);
    if (r) loans.reload();
  }
  return (
    <div>
      <PageHeader eyebrow="My library" title="My loans" description="Renew before the due date if nobody else is waiting. Overdue books cannot be renewed." />
      <div className="card p-4">
        <div className="mb-3"><Tabs label="Loans" value={tab} onChange={(t) => { setTab(t); setPage(1); }} options={[{ value: "active", label: "On loan" }, { value: "all", label: "Full history" }]} /></div>
        <Async state={loans} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title={tab === "active" ? "You have no books on loan" : "No loan history yet"} />}>
          {(p) => (
            <>
              <TableWrap label="My loans">
                <table className="table-base">
                  <thead><tr><th>Title</th><th>Issued</th><th>Due</th><th>Fine</th><th className="text-right">Actions</th></tr></thead>
                  <tbody>{p.items.map((l) => (
                    <tr key={l.id}>
                      <td><button className="text-left font-medium hover:text-accent hover:underline" onClick={() => setDetail(l.id)}>{l.title}</button><p className="text-xs text-muted">{l.author}</p></td>
                      <td className="whitespace-nowrap text-xs">{fmtDate(l.issued_on)}</td>
                      <td className="whitespace-nowrap text-xs">{fmtDate(l.due_on)}{l.status === "active" && <p className={cx((l.days_until_due ?? 0) < 0 ? "text-crit" : "text-muted")}>{dueText(l.days_until_due)}</p>}</td>
                      <td className="num font-mono text-xs">{l.fine_amount ? rupees(l.fine_amount) : "—"}</td>
                      <td className="text-right">{l.status === "active"
                        ? <button className="btn-secondary px-2.5 py-1 text-xs" disabled={(l.days_until_due ?? 0) < 0} onClick={() => renew(l.id)}>Renew</button>
                        : <StatusBadge status={l.status} label={l.days_late ? `${l.days_late}d late` : l.status} />}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </TableWrap>
              <Pagination page={p.page} pageSize={p.page_size} total={p.total} onPage={setPage} />
            </>
          )}
        </Async>
      </div>
      {detail !== null && <LoanDetailModal id={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
