/**
 * Client-side mirror of the agent's transparent scoring maths, used for live
 * previews (weight editor, fuzzy playground). The backend remains the source of
 * truth; tests pin both to the same reference values.
 */
import type { Level } from "./types";

export type Weights = Record<"urgency" | "overdue" | "demand" | "fine" | "risk" | "history", number>;

export const KIND_URGENCY: Record<string, number> = {
  recall: 1.0, overdue: 0.8, reservation_ready: 0.7, pickup_reminder: 0.65, fine_notice: 0.5, due_soon: 0.45, early_reminder: 0.3,
};

export interface ScoreInputs { kind: string; daysOverdue: number; demand: number; fine: number; risk: number; lateRate: number }

const clamp01 = (x: number) => Math.min(Math.max(x, 0), 1);

export function normalise(i: ScoreInputs): Weights {
  return {
    urgency: KIND_URGENCY[i.kind] ?? 0.4,
    overdue: clamp01(i.daysOverdue / 30),
    demand: clamp01(i.demand / 5),
    fine: clamp01(i.fine / 500),
    risk: clamp01(i.risk),
    history: clamp01(i.lateRate),
  };
}

/** score = Σ wₖ·xₖ with weights rescaled to sum to 100. */
export function utilityScore(i: ScoreInputs, weights: Weights): { score: number; parts: { factor: keyof Weights; weight: number; value: number; contribution: number }[] } {
  const total = Object.values(weights).reduce((a, w) => a + Math.max(w, 0), 0) || 1;
  const x = normalise(i);
  let exact = 0;
  const parts = (Object.keys(x) as (keyof Weights)[]).map((k) => {
    const w = (Math.max(weights[k] ?? 0, 0) * 100) / total;
    exact += w * x[k]; // sum unrounded contributions, exactly like the backend
    return { factor: k, weight: round(w), value: round(x[k], 3), contribution: round(w * x[k]) };
  });
  return { score: round(Math.min(exact, 100)), parts };
}

export function round(n: number, digits = 2): number {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}

export function trapezoid(x: number, a: number, b: number, c: number, d: number): number {
  if (x < a || x > d) return 0;
  if (x >= b && x <= c) return 1;
  if (x < b) return b === a ? 1 : (x - a) / (b - a);
  return d === c ? 1 : (d - x) / (d - c);
}

export const triangle = (x: number, a: number, b: number, c: number) => trapezoid(x, a, b, b, c);

const INF = Number.POSITIVE_INFINITY;

export const LATENESS_SETS = {
  early: (x: number) => trapezoid(x, -INF, -INF, -4, -2),
  due_soon: (x: number) => triangle(x, -3, -1, 1),
  slightly_overdue: (x: number) => triangle(x, 0, 3, 7),
  moderately_overdue: (x: number) => triangle(x, 5, 10, 16),
  severely_overdue: (x: number) => trapezoid(x, 13, 20, INF, INF),
};

export const LEVEL_RANK: Record<Level, number> = { Low: 0, Medium: 1, High: 2, Critical: 3 };

/** Heap ordering key used by the notification queue: level first, then score (higher first). */
export function compareQueueItems(a: { level: Level; score: number }, b: { level: Level; score: number }): number {
  return LEVEL_RANK[b.level] - LEVEL_RANK[a.level] || b.score - a.score;
}

export function weightsValid(w: Partial<Weights>): string | null {
  const keys: (keyof Weights)[] = ["urgency", "overdue", "demand", "fine", "risk", "history"];
  for (const k of keys) {
    const v = w[k];
    if (v === undefined || Number.isNaN(v)) return `Weight “${k}” is required`;
    if (v < 0 || v > 100) return `Weight “${k}” must be between 0 and 100`;
  }
  if (keys.reduce((a, k) => a + (w[k] ?? 0), 0) <= 0) return "At least one weight must be positive";
  return null;
}
