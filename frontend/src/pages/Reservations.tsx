import { useMemo, useState } from "react";
import { useUser } from "../context/AuthContext";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { post, qs } from "../lib/api";
import { fmtDate, humanise } from "../lib/format";
import type { Reservation } from "../lib/types";
import { Async, Card, EmptyState, PageHeader, StatusBadge, Tabs } from "../components/ui";
import { useAction } from "../components/toast";

export default function Reservations() {
  const user = useUser();
  const { tick, bump } = useAgent();
  const [status, setStatus] = useState<"open" | "fulfilled" | "expired" | "cancelled" | "all">("open");
  const state = useApi<{ items: Reservation[] }>(`/api/reservations${qs({ status })}`, [tick]);
  const act = useAction();
  const grouped = useMemo(() => {
    const g = new Map<number, { title: string; author: string; items: Reservation[] }>();
    for (const r of state.data?.items ?? []) {
      if (!g.has(r.book_id)) g.set(r.book_id, { title: r.title, author: r.author, items: [] });
      g.get(r.book_id)!.items.push(r);
    }
    return [...g.entries()];
  }, [state.data]);

  async function cancel(id: number) {
    if (!window.confirm("Cancel this reservation? A held copy will pass to the next member.")) return;
    const r = await act(() => post(`/api/reservations/${id}/cancel`), "Reservation cancelled");
    if (r) { state.reload(); bump(); }
  }

  return (
    <div>
      <PageHeader eyebrow="Queue" title="Reservations"
        description={user.role === "member" ? "Your place in each queue. When a copy is returned the agent holds it for the first member and notifies them." :
          "First-come-first-served queues per title. Returned copies are allocated automatically; uncollected holds expire and pass on (rule R31)."} />
      <div className="mb-4"><Tabs label="Reservation status" value={status} onChange={setStatus} options={[
        { value: "open", label: "Open" }, { value: "fulfilled", label: "Fulfilled" }, { value: "expired", label: "Expired" }, { value: "cancelled", label: "Cancelled" }, { value: "all", label: "All" }]} /></div>
      <Async state={state} isEmpty={(d) => d.items.length === 0} empty={<EmptyState title="No reservations here">{user.role === "member" ? "Reserve a book from the catalog when all copies are out." : null}</EmptyState>}>
        {() => (
          <div className="grid gap-4 lg:grid-cols-2">
            {grouped.map(([bookId, g]) => (
              <Card key={bookId} title={g.title} subtitle={g.author}>
                <ol className="space-y-2">
                  {g.items.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                      <div className="min-w-0">
                        <p className="font-medium">{r.position ? <span className="mr-2 font-mono text-xs text-muted">#{r.position}</span> : null}{r.member_name}
                          <span className="ml-1 text-xs text-muted">{humanise(r.member_type)}</span></p>
                        <p className="text-xs text-muted">Placed {fmtDate(r.created_on)}{r.status === "ready" && ` · copy ${r.copy_barcode} held until ${fmtDate(r.expires_on)}`}{r.closed_on && ` · closed ${fmtDate(r.closed_on)}`}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={r.status} />
                        {["waiting", "ready"].includes(r.status) && <button className="btn-ghost px-2 py-1 text-xs" onClick={() => cancel(r.id)}>Cancel</button>}
                      </div>
                    </li>
                  ))}
                </ol>
              </Card>
            ))}
          </div>
        )}
      </Async>
    </div>
  );
}
