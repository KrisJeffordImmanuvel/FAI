import { useState } from "react";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { qs } from "../lib/api";
import { fmtDate } from "../lib/format";
import { Async, EmptyState, PageHeader, TableWrap } from "../components/ui";

interface AuditRow { id: number; created_at: string; sim_date: string; actor: string; action: string; entity: string; entity_id: number | null; details: Record<string, unknown> }

const PREFIXES = ["", "loan", "reservation", "fine", "approval", "member", "kb", "ml", "settings", "policy", "agent", "clock", "auth", "book", "user"];

export default function Audit() {
  const { tick } = useAgent();
  const [action, setAction] = useState("");
  const state = useApi<AuditRow[]>(`/api/admin/audit${qs({ limit: 300, action })}`, [tick]);
  return (
    <div>
      <PageHeader eyebrow="Accountability" title="Audit log" description="Every change made by people or the agent, with the simulated date it happened."
        actions={<label><span className="sr-only">Filter by action</span><select className="input" value={action} onChange={(e) => setAction(e.target.value)}>
          {PREFIXES.map((p) => <option key={p} value={p}>{p ? `${p}.*` : "All actions"}</option>)}</select></label>} />
      <div className="card p-4">
        <Async state={state} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No audit entries" />}>
          {(rows) => (
            <TableWrap label="Audit log">
              <table className="table-base">
                <thead><tr><th>Sim date</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.id}>
                    <td className="whitespace-nowrap text-xs">{fmtDate(r.sim_date)}</td>
                    <td className="whitespace-nowrap text-xs">{r.actor}</td>
                    <td><code className="font-mono text-xs">{r.action}</code></td>
                    <td className="whitespace-nowrap font-mono text-xs">{r.entity}{r.entity_id ? ` #${r.entity_id}` : ""}</td>
                    <td className="max-w-md break-words font-mono text-[11px] text-ink2">{Object.entries(r.details).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ")}</td>
                  </tr>
                ))}</tbody>
              </table>
            </TableWrap>
          )}
        </Async>
      </div>
    </div>
  );
}
