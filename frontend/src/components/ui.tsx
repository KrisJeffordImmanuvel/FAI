import { useEffect, useId, useRef, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Info, Loader2, X, XCircle } from "lucide-react";
import type { ApiState } from "../lib/useApi";
import type { Level } from "../lib/types";
import { humanise } from "../lib/format";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
        <h1 className="text-3xl font-semibold leading-tight sm:text-[2.1rem]">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm text-ink2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ title, subtitle, actions, children, className, bodyClass }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={cx("card", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="font-display text-lg font-semibold leading-snug">{title}</h2>}
            {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={cx("p-4", bodyClass)}>{children}</div>
    </section>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line px-4 py-10 text-center">
      <div className="text-muted" aria-hidden>{icon ?? <Info className="h-6 w-6" />}</div>
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-md text-sm text-ink2">{children}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-crit/40 bg-crit/5 p-4 text-sm sm:flex-row sm:items-center">
      <XCircle className="h-5 w-5 shrink-0 text-crit" aria-hidden />
      <p className="flex-1">{message}</p>
      {onRetry && <button className="btn-secondary" onClick={onRetry}>Try again</button>}
    </div>
  );
}

/** Renders loading / error / empty states around an API resource. */
export function Async<T>({ state, children, empty, isEmpty }: {
  state: ApiState<T>; children: (data: T) => ReactNode; empty?: ReactNode; isEmpty?: (d: T) => boolean;
}) {
  if (state.error && !state.data) return <ErrorState message={state.error} onRetry={state.reload} />;
  if (!state.data) return <Spinner />;
  if (isEmpty && isEmpty(state.data)) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;
  return <>{children(state.data)}</>;
}

const LEVEL_STYLE: Record<Level, string> = {
  Critical: "bg-crit/10 text-ink border-crit/50",
  High: "bg-high/15 text-ink border-high/60",
  Medium: "bg-med/15 text-ink border-med/70",
  Low: "bg-low/10 text-ink border-low/50",
};
const LEVEL_DOT: Record<Level, string> = { Critical: "bg-crit", High: "bg-high", Medium: "bg-med", Low: "bg-low" };

export function LevelBadge({ level, score }: { level: Level; score?: number }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium", LEVEL_STYLE[level])}>
      <span className={cx("h-2 w-2 rounded-full", LEVEL_DOT[level])} aria-hidden />
      {level}
      {score !== undefined && <span className="num font-mono text-[11px] text-ink2">{score.toFixed(1)}</span>}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  active: "good", available: "good", paid: "good", approved: "good", fulfilled: "good", returned: "neutral", sent: "good", read: "neutral", resolved: "good",
  ready: "teal", on_hold: "teal", waiting: "neutral", queued: "warn", pending: "warn", accruing: "warn", partially_paid: "warn", open: "warn",
  on_loan: "neutral", overdue: "crit", restricted: "crit", suspended: "crit", lost: "crit", rejected: "neutral", suppressed: "neutral", cancelled: "neutral",
  expired: "neutral", waived: "teal", maintenance: "neutral", withdrawn: "neutral", "n/a": "neutral", ignored: "neutral",
};
const TONE_CLASS: Record<string, string> = {
  good: "bg-good/10 text-good border-good/30",
  teal: "bg-teal/10 text-teal border-teal/30",
  warn: "bg-med/15 text-ink border-med/50",
  crit: "bg-crit/10 text-crit border-crit/30",
  neutral: "bg-sunken text-ink2 border-line",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return (
    <span className={cx("inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium capitalize", TONE_CLASS[tone])}>
      {label ?? humanise(status).toLowerCase()}
    </span>
  );
}

export function Kpi({ label, value, hint, icon, tone = "ink" }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "ink" | "accent" | "crit" | "teal" }) {
  const toneClass = { ink: "text-ink", accent: "text-accent", crit: "text-crit", teal: "text-teal" }[tone];
  return (
    <div className="card catalog-card flex flex-col gap-1 px-4 pb-6 pt-3">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        {icon && <span className="text-muted" aria-hidden>{icon}</span>}
      </div>
      <span className={cx("font-display text-3xl font-semibold leading-none", toneClass)}>{value}</span>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}

export function Field({ label, error, hint, children, htmlFor }: { label: string; error?: string | null; hint?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p className="mt-1 text-xs font-medium text-crit" role="alert">{error}</p>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && ref.current) {
        const f = ref.current.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (!f.length) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
      }
    };
    document.addEventListener("keydown", onKey);
    const t = window.setTimeout(() => ref.current?.querySelector<HTMLElement>("input, select, textarea, button:not([data-close])")?.focus(), 30);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      window.clearTimeout(t);
      document.body.style.overflow = "";
      prev?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className={cx("card animate-slide-in max-h-[92vh] w-full overflow-y-auto rounded-b-none sm:rounded-xl", wide ? "sm:max-w-4xl" : "sm:max-w-lg")}>
        <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-line bg-surface px-4 py-3">
          <h2 id={titleId} className="font-display text-lg font-semibold">{title}</h2>
          <button data-close className="btn-ghost p-1.5" onClick={onClose} aria-label="Close dialog"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "success" | "warn" | "error"; children: ReactNode }) {
  const map = {
    info: ["border-teal/30 bg-teal/5", <Info key="i" className="h-4 w-4 text-teal" />],
    success: ["border-good/30 bg-good/5", <CheckCircle2 key="s" className="h-4 w-4 text-good" />],
    warn: ["border-med/50 bg-med/10", <AlertTriangle key="w" className="h-4 w-4 text-ink" />],
    error: ["border-crit/40 bg-crit/5", <XCircle key="e" className="h-4 w-4 text-crit" />],
  } as const;
  const [cls, icon] = map[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("flex items-start gap-2 rounded-lg border px-3 py-2 text-sm", cls)}>
      <span className="mt-0.5 shrink-0" aria-hidden>{icon}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-line bg-sunken/70 p-1">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={cx("rounded-md px-3 py-1.5 text-sm transition", value === o.value ? "bg-surface font-medium text-ink shadow-card" : "text-ink2 hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav className="flex items-center justify-between gap-2 pt-3 text-sm" aria-label="Pagination">
      <span className="text-muted">Page {page} of {pages} · {total} total</span>
      <div className="flex gap-1">
        <button className="btn-secondary px-2" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
        <button className="btn-secondary px-2" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
      </div>
    </nav>
  );
}

/** Horizontally scrollable table wrapper so wide tables never cause page scroll on phones. */
export function TableWrap({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className="relative -mx-4 overflow-x-auto px-4" role="region" aria-label={label} tabIndex={label ? 0 : undefined}>
      {children}
    </div>
  );
}

export function RiskPill({ score, label }: { score?: number | null; label?: string | null }) {
  if (score === null || score === undefined) return <span className="text-xs text-muted">—</span>;
  const tone = label === "high" ? "bg-crit" : label === "medium" ? "bg-med" : "bg-good";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs" title="Predicted late-return risk (decision support only)">
      <span className="relative h-1.5 w-10 overflow-hidden rounded-full bg-sunken" aria-hidden>
        <span className={cx("absolute inset-y-0 left-0 rounded-full", tone)} style={{ width: `${Math.round(score * 100)}%` }} />
      </span>
      <span className="num font-mono">{Math.round(score * 100)}%</span>
      <span className="text-muted">{label}</span>
    </span>
  );
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5 text-sm">
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
