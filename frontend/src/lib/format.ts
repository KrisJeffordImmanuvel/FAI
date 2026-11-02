import type { Level } from "./types";

export const rupees = (n: number | null | undefined): string =>
  `₹${(n ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

export const pct = (n: number | null | undefined, digits = 0): string => `${((n ?? 0) * 100).toFixed(digits)}%`;

export function fmtDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", opts);
}

export const shortDate = (iso: string | null | undefined) => fmtDate(iso, { day: "numeric", month: "short" });

export const humanise = (s: string | null | undefined): string =>
  (s ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const KIND_LABELS: Record<string, string> = {
  due_soon: "Due soon",
  early_reminder: "Early reminder",
  overdue: "Overdue notice",
  recall: "Recall",
  fine_notice: "Fine summary",
  reservation_ready: "Reservation ready",
  pickup_reminder: "Pickup reminder",
};

export const CHANNEL_LABELS: Record<string, string> = { in_app: "In-app", email: "Email (simulated)", sms: "SMS (simulated)" };

export const LEVEL_ORDER: Level[] = ["Critical", "High", "Medium", "Low"];

/** Relative due-date wording used across loan tables. */
export function dueText(daysUntilDue: number | undefined): string {
  if (daysUntilDue === undefined) return "";
  if (daysUntilDue < 0) return `${-daysUntilDue} day${daysUntilDue === -1 ? "" : "s"} overdue`;
  if (daysUntilDue === 0) return "Due today";
  if (daysUntilDue === 1) return "Due tomorrow";
  return `Due in ${daysUntilDue} days`;
}

export const ALGO_LABELS: Record<string, string> = { logistic_regression: "Logistic Regression", decision_tree: "Decision Tree" };
