/**
 * Chart primitives following the data-viz rules: validated categorical palette,
 * thin marks, hairline grid, legend for ≥2 series, hover tooltips and a table
 * view on every chart (the light palette has sub-3:1 slots → relief required).
 */
import { useState, type ReactNode } from "react";
import { Table2, BarChart3 } from "lucide-react";
import { Card, TableWrap } from "./ui";

export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)", "var(--series-6)"];
export const LEVEL_COLORS: Record<string, string> = { Critical: "rgb(var(--crit))", High: "rgb(var(--high))", Medium: "rgb(var(--med))", Low: "rgb(var(--low))" };

export const axisProps = {
  stroke: "var(--chart-axis)",
  tick: { fill: "var(--chart-text)", fontSize: 11 },
  tickLine: false,
} as const;
export const gridProps = { stroke: "var(--chart-grid)", strokeDasharray: undefined, vertical: false } as const;

export function ChartTooltip({ active, payload, label, format }: {
  active?: boolean; payload?: { name: string; value: number; color: string; dataKey: string }[]; label?: string; format?: (v: number, key: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card px-3 py-2 text-xs shadow-lift">
      {label !== undefined && <p className="mb-1 font-medium text-ink">{label}</p>}
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-ink2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} aria-hidden />
          <span>{p.name}</span>
          <span className="num ml-auto pl-3 font-mono text-ink">{format ? format(p.value, p.dataKey) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  if (items.length < 2) return null;
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2" aria-label="Legend">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} aria-hidden />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

/** Card with a chart ↔ table toggle. `columns` drive the accessible table view. */
export function ChartCard<Row extends Record<string, unknown>>({ title, subtitle, rows, columns, legend, children, height = 240, actions }: {
  title: string; subtitle?: string; rows: Row[]; columns: { key: keyof Row & string; label: string; format?: (v: unknown) => string }[];
  legend?: { label: string; color: string }[]; children: ReactNode; height?: number; actions?: ReactNode;
}) {
  const [table, setTable] = useState(false);
  return (
    <Card title={title} subtitle={subtitle} actions={
      <>
        {actions}
        <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setTable((t) => !t)} aria-pressed={table} aria-label={table ? "Show chart" : "Show as table"}>
          {table ? <BarChart3 className="h-3.5 w-3.5" /> : <Table2 className="h-3.5 w-3.5" />}
          {table ? "Chart" : "Table"}
        </button>
      </>
    }>
      {rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted">No data for this period yet — run the agent or advance the clock.</p>
      ) : table ? (
        <TableWrap label={`${title} data`}>
          <table className="table-base num">
            <thead><tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>{columns.map((c) => <td key={c.key}>{c.format ? c.format(r[c.key]) : String(r[c.key] ?? "—")}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <>
          {legend && <Legend items={legend} />}
          <div style={{ height }} className="w-full">{children}</div>
        </>
      )}
    </Card>
  );
}
