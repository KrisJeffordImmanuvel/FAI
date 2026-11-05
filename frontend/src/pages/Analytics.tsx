import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAgent } from "../context/AgentContext";
import { useApi } from "../lib/useApi";
import { CHANNEL_LABELS, KIND_LABELS, humanise, pct, rupees, shortDate } from "../lib/format";
import { Async, Card, Kpi, PageHeader, Tabs } from "../components/ui";
import { axisProps, ChartCard, ChartTooltip, gridProps, SERIES } from "../components/charts";

interface Full {
  sim_date: string;
  overdue_trend: { date: string; overdue: number }[];
  fine_collections: { week: string; collected: number; waived: number; assessed: number }[];
  popular_books: { title: string; category: string; loans: number }[];
  demand_by_category: { category: string; loans: number; reservations: number }[];
  notification_outcomes: { kind: string; resolved: number; pending: number; suppressed: number; queued: number }[];
  avg_days_to_resolve: number | null;
  channels: Record<string, number>;
  late_rate_by_type: { member_type: string; loans: number; late_rate: number }[];
  circulation: { week: string; issued: number; returned: number }[];
  risk_distribution: Record<string, number>;
}

const short = (s: string, n = 26) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export default function Analytics() {
  const { tick } = useAgent();
  const [days, setDays] = useState<"30" | "60" | "120">("60");
  const state = useApi<Full>(`/api/analytics/full?days=${days}`, [tick]);
  return (
    <div>
      <PageHeader eyebrow="Insight" title="Analytics" description="Circulation, fines, demand and how members respond to the agent's notifications."
        actions={<Tabs label="Period" value={days} onChange={setDays} options={[{ value: "30", label: "30 days" }, { value: "60", label: "60 days" }, { value: "120", label: "120 days" }]} />} />
      <Async state={state}>
        {(d) => {
          const resolved = d.notification_outcomes.reduce((a, o) => a + o.resolved, 0);
          const delivered = d.notification_outcomes.reduce((a, o) => a + o.resolved + o.pending, 0);
          const suppressed = d.notification_outcomes.reduce((a, o) => a + o.suppressed, 0);
          const collected = d.fine_collections.reduce((a, w) => a + w.collected, 0);
          const outcomes = d.notification_outcomes.map((o) => ({ ...o, label: KIND_LABELS[o.kind] ?? o.kind }));
          const channels = Object.entries(d.channels).map(([k, v]) => ({ channel: CHANNEL_LABELS[k] ?? k, count: v }));
          return (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Kpi label="Fines collected" value={rupees(collected)} hint={`last ${days} days`} tone="accent" />
                <Kpi label="Notice resolution" value={delivered ? pct(resolved / delivered) : "—"} hint={`${resolved} of ${delivered} delivered notices led to action`} tone="teal" />
                <Kpi label="Avg. days to act" value={d.avg_days_to_resolve ?? "—"} hint="from notice to return / pickup / payment" />
                <Kpi label="Spam prevented" value={suppressed} hint="suppressed by cooldown, duplicate or daily-limit checks" />
              </div>
              <div className="grid gap-6 xl:grid-cols-2">
                <ChartCard title="Overdue trend" subtitle="Loans past due on each simulated day" rows={d.overdue_trend} columns={[{ key: "date", label: "Date" }, { key: "overdue", label: "Overdue" }]}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={d.overdue_trend} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="date" tickFormatter={shortDate} {...axisProps} minTickGap={24} />
                      <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
                      <Tooltip content={<ChartTooltip />} labelFormatter={shortDate} />
                      <Area type="monotone" dataKey="overdue" name="Overdue loans" stroke={SERIES[1]} strokeWidth={2} fill={SERIES[1]} fillOpacity={0.1} />
                    </AreaChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Fine collections by week" subtitle="Assessed vs collected vs waived" rows={d.fine_collections}
                  legend={[{ label: "Assessed", color: SERIES[0] }, { label: "Collected", color: SERIES[2] }, { label: "Waived", color: SERIES[3] }]}
                  columns={[{ key: "week", label: "Week of" }, { key: "assessed", label: "Assessed", format: (v) => rupees(v as number) }, { key: "collected", label: "Collected", format: (v) => rupees(v as number) }, { key: "waived", label: "Waived", format: (v) => rupees(v as number) }]}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.fine_collections} margin={{ top: 8, right: 8, bottom: 0, left: -10 }} barGap={2} barCategoryGap="25%">
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="week" tickFormatter={shortDate} {...axisProps} minTickGap={12} />
                      <YAxis {...axisProps} axisLine={false} tickFormatter={(v) => `₹${v}`} />
                      <Tooltip content={<ChartTooltip format={(v) => rupees(v)} />} labelFormatter={(l) => `Week of ${shortDate(l)}`} cursor={{ fill: "rgb(var(--sunken))" }} />
                      <Bar dataKey="assessed" name="Assessed" fill={SERIES[0]} maxBarSize={18} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="collected" name="Collected" fill={SERIES[2]} maxBarSize={18} radius={[4, 4, 0, 0]} />
                      <Bar dataKey="waived" name="Waived" fill={SERIES[3]} maxBarSize={18} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Most borrowed titles" subtitle="All time" rows={d.popular_books} height={300} columns={[{ key: "title", label: "Title" }, { key: "category", label: "Category" }, { key: "loans", label: "Loans" }]}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.popular_books} layout="vertical" margin={{ top: 0, right: 24, bottom: 0, left: 8 }}>
                      <CartesianGrid {...gridProps} horizontal={false} vertical />
                      <XAxis type="number" allowDecimals={false} {...axisProps} />
                      <YAxis type="category" dataKey="title" width={170} tickFormatter={(t) => short(t)} {...axisProps} axisLine={false} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(var(--sunken))" }} />
                      <Bar dataKey="loans" name="Loans" fill={SERIES[0]} maxBarSize={16} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Demand by category" subtitle={`Loans and reservations, last ${days} days`} rows={d.demand_by_category} height={300}
                  legend={[{ label: "Loans", color: SERIES[0] }, { label: "Reservations", color: SERIES[1] }]}
                  columns={[{ key: "category", label: "Category" }, { key: "loans", label: "Loans" }, { key: "reservations", label: "Reservations" }]}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.demand_by_category} layout="vertical" margin={{ top: 0, right: 24, bottom: 0, left: 8 }} barGap={2}>
                      <CartesianGrid {...gridProps} horizontal={false} vertical />
                      <XAxis type="number" allowDecimals={false} {...axisProps} />
                      <YAxis type="category" dataKey="category" width={150} tickFormatter={(t) => short(t, 22)} {...axisProps} axisLine={false} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(var(--sunken))" }} />
                      <Bar dataKey="loans" name="Loans" fill={SERIES[0]} maxBarSize={12} radius={[0, 4, 4, 0]} />
                      <Bar dataKey="reservations" name="Reservations" fill={SERIES[1]} maxBarSize={12} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Notification outcomes" subtitle="Did the member act after being notified?" rows={outcomes} height={280}
                  legend={[{ label: "Resolved", color: SERIES[2] }, { label: "No action yet", color: SERIES[3] }, { label: "Suppressed (anti-spam)", color: "rgb(var(--low))" }]}
                  columns={[{ key: "label", label: "Type" }, { key: "resolved", label: "Resolved" }, { key: "pending", label: "No action yet" }, { key: "suppressed", label: "Suppressed" }]}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={outcomes} margin={{ top: 8, right: 8, bottom: 0, left: -18 }} barCategoryGap="30%">
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="label" {...axisProps} interval={0} tick={{ ...axisProps.tick, fontSize: 10 }} tickFormatter={(t) => short(t, 12)} />
                      <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(var(--sunken))" }} />
                      <Bar dataKey="resolved" name="Resolved" stackId="o" fill={SERIES[2]} maxBarSize={24} stroke="rgb(var(--surface))" strokeWidth={1} />
                      <Bar dataKey="pending" name="No action yet" stackId="o" fill={SERIES[3]} maxBarSize={24} stroke="rgb(var(--surface))" strokeWidth={1} />
                      <Bar dataKey="suppressed" name="Suppressed" stackId="o" fill="rgb(var(--low))" maxBarSize={24} stroke="rgb(var(--surface))" strokeWidth={1} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Weekly circulation" subtitle="Books issued vs returned" rows={d.circulation} height={280}
                  legend={[{ label: "Issued", color: SERIES[0] }, { label: "Returned", color: SERIES[2] }]}
                  columns={[{ key: "week", label: "Week of" }, { key: "issued", label: "Issued" }, { key: "returned", label: "Returned" }]}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={d.circulation} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="week" tickFormatter={shortDate} {...axisProps} minTickGap={12} />
                      <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
                      <Tooltip content={<ChartTooltip />} labelFormatter={(l) => `Week of ${shortDate(l)}`} />
                      <Line dataKey="issued" name="Issued" stroke={SERIES[0]} strokeWidth={2} dot={{ r: 3 }} />
                      <Line dataKey="returned" name="Returned" stroke={SERIES[2]} strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                <Card title="Delivery channels">
                  <ul className="space-y-2 text-sm">{channels.map((c) => <li key={c.channel} className="flex justify-between"><span>{c.channel}</span><span className="num font-mono">{c.count}</span></li>)}</ul>
                </Card>
                <Card title="Late-return rate by member type">
                  <ul className="space-y-2 text-sm">{d.late_rate_by_type.map((r) => <li key={r.member_type} className="flex justify-between"><span>{humanise(r.member_type)} <span className="text-xs text-muted">({r.loans} loans)</span></span><span className="num font-mono">{pct(r.late_rate, 1)}</span></li>)}</ul>
                </Card>
                <Card title="Predicted risk of active loans">
                  <ul className="space-y-2 text-sm">{["high", "medium", "low"].map((k) => <li key={k} className="flex justify-between"><span>{humanise(k)}</span><span className="num font-mono">{d.risk_distribution[k] ?? 0}</span></li>)}</ul>
                  <p className="mt-2 text-xs text-muted">Advisory only — used for gentle early reminders.</p>
                </Card>
              </div>
            </div>
          );
        }}
      </Async>
    </div>
  );
}
