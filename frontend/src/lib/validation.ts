import type { Slab } from "./types";

export const isEmail = (s: string) => /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(s.trim());
export const isPhone = (s: string) => /^\+?[0-9 ]{8,16}$/.test(s.trim());
export const isIsbn = (s: string) => /^\d{10}(\d{3})?$/.test(s.trim());

export function required(value: string, label: string, min = 1): string | null {
  return value.trim().length < min ? (min > 1 ? `${label} must be at least ${min} characters` : `${label} is required`) : null;
}

export function amountError(value: string | number, max: number): string | null {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n <= 0) return "Enter an amount greater than zero";
  if (Math.round(n * 100) > Math.round(max * 100)) return `Amount cannot exceed the balance of ₹${max}`;
  return null;
}

/** Mirrors the backend slab validator: contiguous from day 1, only the last slab open-ended. */
export function slabErrors(slabs: Slab[]): string[] {
  const errors: string[] = [];
  if (!slabs.length) return ["At least one slab is required"];
  let expected = 1;
  slabs.forEach((s, i) => {
    if (s.from_day !== expected) errors.push(`Slab ${i + 1} must start at day ${expected}`);
    if (s.rate < 0) errors.push(`Slab ${i + 1} has a negative rate`);
    if (s.to_day === null) {
      if (i !== slabs.length - 1) errors.push("Only the last slab may be open-ended");
    } else {
      if (s.to_day < s.from_day) errors.push(`Slab ${i + 1} ends before it starts`);
      expected = s.to_day + 1;
    }
  });
  if (slabs[slabs.length - 1].to_day !== null) errors.push("The last slab must be open-ended");
  return errors;
}

export type Errors<T> = Partial<Record<keyof T, string>>;
export function hasErrors<T>(e: Errors<T>): boolean {
  return Object.values(e).some(Boolean);
}
