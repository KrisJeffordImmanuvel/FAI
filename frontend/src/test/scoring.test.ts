import { describe, expect, it } from "vitest";
import { compareQueueItems, LATENESS_SETS, normalise, trapezoid, triangle, utilityScore, weightsValid, type Weights } from "../lib/scoring";
import type { Level } from "../lib/types";

const W: Weights = { urgency: 25, overdue: 20, demand: 20, fine: 10, risk: 15, history: 10 };

describe("utility score (mirror of backend priority.utility_score)", () => {
  it("matches the backend reference value", () => {
    // same inputs as backend test_utility_breakdown_sums_to_score → 54.5
    const r = utilityScore({ kind: "recall", daysOverdue: 15, demand: 2, fine: 100, risk: 0.5, lateRate: 0.2 }, W);
    expect(r.score).toBe(54.5);
    expect(r.parts.reduce((a, p) => a + p.contribution, 0)).toBeCloseTo(54.5, 1);
  });

  it("rescales weights so the maximum is always 100", () => {
    const max = { kind: "recall", daysOverdue: 99, demand: 99, fine: 9999, risk: 1, lateRate: 1 };
    expect(utilityScore(max, W).score).toBe(100);
    expect(utilityScore(max, { ...W, urgency: 75, overdue: 60 }).score).toBe(100);
  });

  it("clamps normalised factors to [0, 1]", () => {
    const n = normalise({ kind: "overdue", daysOverdue: 90, demand: -3, fine: 1000, risk: 1.4, lateRate: -1 });
    expect(n).toEqual({ urgency: 0.8, overdue: 1, demand: 0, fine: 1, risk: 1, history: 0 });
  });

  it("validates weights", () => {
    expect(weightsValid(W)).toBeNull();
    expect(weightsValid({ ...W, risk: -1 })).toMatch(/between 0 and 100/);
    expect(weightsValid({ urgency: 0, overdue: 0, demand: 0, fine: 0, risk: 0, history: 0 })).toMatch(/positive/);
  });
});

describe("fuzzy membership functions", () => {
  it("computes triangles and trapezoids", () => {
    expect(triangle(3, 0, 3, 7)).toBe(1);
    expect(triangle(5, 0, 3, 7)).toBeCloseTo(0.5);
    expect(triangle(-1, 0, 3, 7)).toBe(0);
    expect(trapezoid(30, 13, 20, Infinity, Infinity)).toBe(1);
  });

  it("matches the backend lateness sets", () => {
    expect(LATENESS_SETS.slightly_overdue(3)).toBe(1);
    expect(LATENESS_SETS.moderately_overdue(7)).toBeCloseTo(0.4);
    expect(LATENESS_SETS.severely_overdue(25)).toBe(1);
    expect(LATENESS_SETS.early(-6)).toBe(1);
    expect(LATENESS_SETS.due_soon(-1)).toBe(1);
  });
});

describe("priority queue ordering", () => {
  it("orders by level first, then score", () => {
    const items: { id: string; level: Level; score: number }[] = [
      { id: "low-99", level: "Low", score: 99 },
      { id: "high-40", level: "High", score: 40 },
      { id: "crit-10", level: "Critical", score: 10 },
      { id: "high-70", level: "High", score: 70 },
    ];
    expect([...items].sort(compareQueueItems).map((i) => i.id)).toEqual(["crit-10", "high-70", "high-40", "low-99"]);
  });
});
