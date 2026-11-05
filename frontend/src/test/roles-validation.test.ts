import { describe, expect, it } from "vitest";
import { can, canAccess, navFor } from "../lib/roles";
import { amountError, isEmail, isIsbn, isPhone, slabErrors } from "../lib/validation";
import { dueText, rupees } from "../lib/format";
import { errorMessage, qs } from "../lib/api";

describe("role-based navigation", () => {
  it("gives members only member pages", () => {
    const paths = navFor("member").map((n) => n.to);
    expect(paths).toContain("/my-loans");
    expect(paths).not.toContain("/members");
    expect(paths).not.toContain("/agent");
    expect(paths).not.toContain("/admin");
  });

  it("restricts routes including detail routes", () => {
    expect(canAccess("member", "/members/3")).toBe(false);
    expect(canAccess("librarian", "/members/3")).toBe(true);
    expect(canAccess("librarian", "/admin")).toBe(false);
    expect(canAccess("admin", "/admin")).toBe(true);
    expect(canAccess("member", "/")).toBe(true);
  });

  it("encodes capability rules", () => {
    expect(can.editKnowledgeBase("librarian")).toBe(false);
    expect(can.editKnowledgeBase("admin")).toBe(true);
    expect(can.decideApprovals("member")).toBe(false);
  });
});

describe("form validation", () => {
  it("validates identifiers", () => {
    expect(isEmail("a@b.co")).toBe(true);
    expect(isEmail("nope")).toBe(false);
    expect(isPhone("+91 98765 43210")).toBe(true);
    expect(isPhone("12ab")).toBe(false);
    expect(isIsbn("9780134610993")).toBe(true);
    expect(isIsbn("978-0134")).toBe(false);
  });

  it("validates payment amounts against the balance", () => {
    expect(amountError("50", 100)).toBeNull();
    expect(amountError("0", 100)).toMatch(/greater than zero/);
    expect(amountError("100.01", 100)).toMatch(/cannot exceed/);
    expect(amountError("abc", 100)).not.toBeNull();
  });

  it("mirrors backend slab validation", () => {
    expect(slabErrors([{ from_day: 1, to_day: 7, rate: 2 }, { from_day: 8, to_day: null, rate: 5 }])).toEqual([]);
    expect(slabErrors([{ from_day: 2, to_day: null, rate: 2 }])[0]).toMatch(/start at day 1/);
    expect(slabErrors([{ from_day: 1, to_day: 7, rate: 2 }])).toContain("The last slab must be open-ended");
    expect(slabErrors([{ from_day: 1, to_day: null, rate: 2 }, { from_day: 2, to_day: null, rate: 3 }])).toContain("Only the last slab may be open-ended");
  });
});

describe("formatting and api helpers", () => {
  it("formats rupees and due text", () => {
    expect(rupees(1234.5)).toBe("₹1,234.5");
    expect(dueText(-3)).toBe("3 days overdue");
    expect(dueText(-1)).toBe("1 day overdue");
    expect(dueText(0)).toBe("Due today");
    expect(dueText(1)).toBe("Due tomorrow");
  });

  it("builds query strings without empty values", () => {
    expect(qs({ q: "ai", page: 2, empty: "", none: null })).toBe("?q=ai&page=2");
    expect(qs({})).toBe("");
  });

  it("extracts readable error messages", () => {
    expect(errorMessage("Plain", "x")).toBe("Plain");
    expect(errorMessage({ message: "Rule is not valid", errors: ["Fairness guard: blocked"] }, "x")).toBe("Rule is not valid — Fairness guard: blocked");
    expect(errorMessage(null, "fallback")).toBe("fallback");
  });
});

describe("password rules (mirror backend)", async () => {
  const { passwordError } = await import("../lib/validation");
  it("requires 8+ characters with letters and digits", () => {
    expect(passwordError("short1")).toMatch(/8 characters/);
    expect(passwordError("password")).toMatch(/letters and digits/);
    expect(passwordError("12345678")).toMatch(/letters and digits/);
    expect(passwordError("Library2026")).toBeNull();
  });
});
