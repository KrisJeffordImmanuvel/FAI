import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlarmClock, BellRing, BookCopy, Cpu, IndianRupee, ShieldAlert, Users } from "lucide-react";
import { useUser } from "../context/AuthContext";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { post } from "../lib/api";
import { dueText, fmtDate, KIND_LABELS, rupees, shortDate } from "../lib/format";
import type { AgentEvent, Cycle, Level, MemberDetail, Notification, Page } from "../lib/types";
import { Async, Card, EmptyState, Kpi, LevelBadge, PageHeader, StatusBadge, TableWrap, cx } from "../components/ui";
import { axisProps, ChartCard, ChartTooltip, gridProps, LEVEL_COLORS, SERIES } from "../components/charts";
import { useAction } from "../components/toast";

interface DashboardData {
  sim_date: string;
  kpis: Record<string, number>;
  copy_status: Record<string, number>;
  overdue_trend: { date: string; overdue: number }[];
  notifications_by_level: ({ date: string } & Record<Level, number>)[];
  recommendations: { loan_id: number; text: string }[];
  recent_events: AgentEvent[];
  last_cycle: Cycle | null;
}

export default function Dashboard() {
  const user = useUser();
  return user.role === "member" ? <MemberDashboard /> : <StaffDashboard />;
}

const PHASE_STYLE: Record<string, string> = {
  perceive: "bg-teal/15 text-teal", think: "bg-sunken text-ink", act: "bg-accent/15 text-accent",
  human: "bg-good/15 text-good", system: "bg-sunken text-ink2", demo: "bg-med/20 text-ink",
};

export function EventItem({ e }: { e: AgentEvent }) {
  const dot = { critical: "bg-crit", warning: "bg-high", success: "bg-good", info: "bg-low" }[e.severity] ?? "bg-low";
  return (
    <li className="flex gap-3 py-2.5">
      <span className={cx("mt-1.5 h-2 w-2 shrink-0 rounded-full", dot)} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cx("rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider", PHASE_STYLE[e.phase] ?? "bg-sunken")}>{e.phase}</span>
          <span className="text-sm font-medium">{e.title}</span>
        </div>
        {e.detail && <p className="mt-0.5 text-xs text-ink2">{e.detail}</p>}
        <p className="mt-0.5 font-mono text-[10px] text-muted">{shortDate(e.sim_date)}{e.cycle_id ? ` · cycle #${e.cycle_id}` : ""}</p>
      </div>
    </li>
  );
}

function StaffDashboard() {
  const { tick } = useAgent();
  const state = useApi<DashboardData>("/api/analytics/dashboard", [tick]);
  return (
    <div>
      <PageHeader eyebrow="Overview" title="Circulation dashboard"
        description="What the agent currently perceives, what it recommends and how the library is doing."
        actions={<Link to="/agent" className="btn-primary"><Cpu className="h-4 w-4" aria-hidden />Agent control</Link>} />
      <Async state={state}>
        {(d) => (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <Kpi label="Active loans" value={d.kpis.active_loans} hint={`${d.kpis.due_soon} due within 2 days`} icon={<BookCopy className="h-4 w-4" />} />
              <Kpi label="Overdue" value={d.kpis.overdue_loans} tone="crit" hint={`${d.kpis.high_risk_active} active loans flagged high-risk`} icon={<AlarmClock className="h-4 w-4" />} />
              <Kpi label="Reservations" value={d.kpis.reservations_waiting} hint={`${d.kpis.holds_ready} hold(s) ready for pickup`} icon={<Users className="h-4 w-4" />} />
              <Kpi label="Unpaid fines" value={rupees(d.kpis.unpaid_fines)} tone="accent" hint={`${rupees(d.kpis.collected_7d)} collected in 7 days`} icon={<IndianRupee className="h-4 w-4" />} />
              <Kpi label="Notices · 7 days" value={d.kpis.notifications_7d} hint={`${d.kpis.suppressed_7d} suppressed as spam`} icon={<BellRing className="h-4 w-4" />} />
              <Kpi label="Needs approval" value={d.kpis.pending_approvals} tone="teal" hint={<Link className="underline" to="/approvals">Review queue</Link>} icon={<ShieldAlert className="h-4 w-4" />} />
            </div>

            <div className="grid gap-6 xl:grid-cols-[1.4fr,1fr]">
              <ChartCard title="Overdue loans · last 30 days" subtitle="Loans past their due date on each simulated day"
                rows={d.overdue_trend} columns={[{ key: "date", label: "Date" }, { key: "overdue", label: "Overdue loans" }]}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={d.overdue_trend} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="date" tickFormatter={shortDate} {...axisProps} minTickGap={24} />
                    <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
                    <Tooltip content={<ChartTooltip />} labelFormatter={shortDate} />
                    <Line type="monotone" dataKey="overdue" name="Overdue loans" stroke={SERIES[1]} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "rgb(var(--surface))" }} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
              <ChartCard title="Notifications sent · by priority" subtitle="Last 14 simulated days"
                rows={d.notifications_by_level} legend={(["Critical", "High", "Medium", "Low"] as Level[]).map((l) => ({ label: l, color: LEVEL_COLORS[l] }))}
                columns={[{ key: "date", label: "Date" }, { key: "Critical", label: "Critical" }, { key: "High", label: "High" }, { key: "Medium", label: "Medium" }, { key: "Low", label: "Low" }]}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.notifications_by_level} margin={{ top: 8, right: 8, bottom: 0, left: -18 }} barCategoryGap="28%">
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="date" tickFormatter={shortDate} {...axisProps} minTickGap={16} />
                    <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
                    <Tooltip content={<ChartTooltip />} labelFormatter={shortDate} cursor={{ fill: "rgb(var(--sunken))" }} />
                    {(["Low", "Medium", "High", "Critical"] as Level[]).map((l, i) => (
                      <Bar key={l} dataKey={l} name={l} stackId="a" fill={LEVEL_COLORS[l]} maxBarSize={24} stroke="rgb(var(--surface))" strokeWidth={1}
                        radius={i === 3 ? [4, 4, 0, 0] : 0} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            <div className="grid gap-6 xl:grid-cols-3">
              <Card title="Agent recommendations" subtitle={d.last_cycle ? `From cycle #${d.last_cycle.id} · ${fmtDate(d.last_cycle.sim_date)}` : "Run a cycle to get recommendations"}>
                {d.recommendations.length === 0 ? (
                  <EmptyState title="No follow-ups recommended">The agent escalates recalls ignored for 7+ days (rule R14).</EmptyState>
                ) : (
                  <ul className="divide-y divide-line">
                    {d.recommendations.map((r) => (
                      <li key={r.loan_id} className="py-2 text-sm"><span className="mr-2 font-mono text-xs text-muted">loan #{r.loan_id}</span>{r.text}</li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card title="Notable agent decisions" subtitle="Warnings, escalations and allocations" actions={<Link className="btn-ghost text-xs" to="/agent">Live feed</Link>} className="xl:col-span-2">
                {d.recent_events.length === 0 ? <EmptyState title="No events yet" /> : <ul className="divide-y divide-line">{d.recent_events.map((e) => <EventItem key={e.id} e={e} />)}</ul>}
              </Card>
            </div>

            <Card title="Collection status" subtitle={`${d.kpis.titles} titles · ${d.kpis.copies} physical copies · ${d.kpis.members} members`}>
              <div className="flex flex-wrap gap-3">
                {Object.entries(d.copy_status).map(([status, n]) => (
                  <div key={status} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2"><StatusBadge status={status} /><span className="num font-mono">{n}</span></div>
                ))}
              </div>
            </Card>
          </div>
        )}
      </Async>
    </div>
  );
}

function MemberDashboard() {
  const { tick } = useAgent();
  const state = useApi<MemberDetail>("/api/me/summary", [tick]);
  const notes = useApi<Page<Notification>>("/api/notifications?page_size=5", [tick]);
  const act = useAction();

  async function renew(id: number) {
    const ok = await act(() => post(`/api/loans/${id}/renew`), "Loan renewed — new due date saved");
    if (ok) state.reload();
  }

  return (
    <div>
      <PageHeader eyebrow="My library" title={`Hello, ${useUser().name.split(" ")[0]}`} description="Your loans, reservations, fines and messages from the library agent." />
      <Async state={state}>
        {(m) => (
          <div className="space-y-6">
            {m.status !== "active" && <div className="card border-crit/40 p-4 text-sm"><strong>Borrowing is {m.status}.</strong> {m.restriction_reason}</div>}
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Kpi label="On loan" value={`${m.stats.active_loans}/${m.policy.max_loans}`} hint={`${m.policy.loan_days}-day loans · ${m.policy.max_renewals} renewals`} />
              <Kpi label="Overdue" value={m.stats.overdue_loans} tone={m.stats.overdue_loans ? "crit" : "ink"} hint={`${m.policy.grace_days}-day grace period`} />
              <Kpi label="Unpaid fines" value={rupees(m.stats.unpaid_fines)} tone="accent" hint={<Link className="underline" to="/fines">See itemised fines</Link>} />
              <Kpi label="Unread messages" value={m.unread_notifications ?? 0} tone="teal" hint={<Link className="underline" to="/notifications">Open inbox</Link>} />
            </div>
            <div className="grid gap-6 xl:grid-cols-[1.4fr,1fr]">
              <Card title="Books on loan" actions={<Link className="btn-ghost text-xs" to="/catalog">Browse catalog</Link>}>
                {m.active_loans.length === 0 ? <EmptyState title="No books on loan">Find something in the catalog and reserve it.</EmptyState> : (
                  <TableWrap label="Books on loan">
                    <table className="table-base">
                      <thead><tr><th>Title</th><th>Due</th><th>Status</th><th className="text-right">Action</th></tr></thead>
                      <tbody>
                        {m.active_loans.map((l) => (
                          <tr key={l.id}>
                            <td><p className="font-medium">{l.title}</p><p className="text-xs text-muted">{l.author}</p></td>
                            <td className="whitespace-nowrap">{fmtDate(l.due_on)}</td>
                            <td><span className={cx("text-xs font-medium", (l.days_until_due ?? 0) < 0 ? "text-crit" : (l.days_until_due ?? 9) <= 2 ? "text-ink" : "text-ink2")}>{dueText(l.days_until_due)}</span>
                              {l.fine_amount > 0 && <p className="text-xs text-muted">Fine so far {rupees(l.fine_amount)}</p>}</td>
                            <td className="text-right">
                              <button className="btn-secondary px-2.5 py-1 text-xs" onClick={() => renew(l.id)} disabled={(l.days_until_due ?? 0) < 0 || l.renewals >= m.policy.max_renewals}
                                title={(l.days_until_due ?? 0) < 0 ? "Overdue loans cannot be renewed" : `${m.policy.max_renewals - l.renewals} renewal(s) left`}>Renew</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableWrap>
                )}
              </Card>
              <Card title="Latest messages" actions={<Link className="btn-ghost text-xs" to="/notifications">All</Link>}>
                <Async state={notes} isEmpty={(p) => p.items.length === 0} empty={<EmptyState title="No messages yet" />}>
                  {(p) => (
                    <ul className="divide-y divide-line">
                      {p.items.map((n) => (
                        <li key={n.id} className="py-2.5">
                          <div className="flex flex-wrap items-center gap-2"><LevelBadge level={n.level} /><span className="text-xs text-muted">{KIND_LABELS[n.kind]} · {shortDate(n.sent_on)}</span></div>
                          <p className={cx("mt-1 text-sm", !n.read && "font-medium")}>{n.subject}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Async>
              </Card>
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              <Card title="Reservations" actions={<Link className="btn-ghost text-xs" to="/reservations">Manage</Link>}>
                {m.reservations.filter((r) => ["waiting", "ready"].includes(r.status)).length === 0 ? <EmptyState title="No open reservations" /> : (
                  <ul className="divide-y divide-line">
                    {m.reservations.filter((r) => ["waiting", "ready"].includes(r.status)).map((r) => (
                      <li key={r.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                        <span className="min-w-0 truncate">{r.title}</span>
                        {r.status === "ready" ? <StatusBadge status="ready" label={`ready · collect by ${shortDate(r.expires_on)}`} /> : <StatusBadge status="waiting" label={`#${r.position} in queue`} />}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card title="Recent history">
                {m.history.length === 0 ? <EmptyState title="No past loans" /> : (
                  <ul className="divide-y divide-line">
                    {m.history.slice(0, 6).map((l) => (
                      <li key={l.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                        <span className="min-w-0 truncate">{l.title}</span>
                        <span className="shrink-0 text-xs text-muted">{l.days_late ? `${l.days_late} day(s) late` : "on time"} · {shortDate(l.returned_on)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>
        )}
      </Async>
    </div>
  );
}
