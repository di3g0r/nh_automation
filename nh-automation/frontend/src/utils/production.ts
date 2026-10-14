import type { AssignmentStatus, MachineState } from "../api/types";

/** Assignment status badge colors (same palette as order statuses). */
export const ASSIGNMENT_COLOR: Record<AssignmentStatus, string> = {
  pending: "blue",
  running: "yellow",
  paused: "orange",
  completed: "teal",
  cancelled: "red",
};

export const MACHINE_STATE_COLOR: Record<MachineState, string> = {
  free: "green",
  busy: "yellow",
  paused: "orange",
  maintenance: "gray",
};

function toCents(value: string): number {
  const n = Number(value);
  return value.trim() === "" || Number.isNaN(n) ? 0 : Math.round(n * 100);
}

export interface SplitSummary {
  /** Sum of the rows, 2 decimals. */
  assigned: string;
  /** Order liters - assigned (negative when over-assigned), 2 decimals. */
  remaining: string;
  /** The split adds up exactly (BR-7). */
  exact: boolean;
}

/** Running total for the "Asignar máquinas" form, computed in cents. */
export function splitSummary(rows: string[], orderLiters: string): SplitSummary {
  const assigned = rows.reduce((acc, v) => acc + toCents(v), 0);
  const remaining = toCents(orderLiters) - assigned;
  return {
    assigned: (assigned / 100).toFixed(2),
    remaining: (remaining / 100).toFixed(2),
    exact: remaining === 0 && assigned > 0,
  };
}

export type DifferenceKind = "faltante" | "excedente" | "none";

/** BR-12: negative = Faltante, positive = Excedente; liters as an absolute value. */
export function differenceKind(difference: string): { kind: DifferenceKind; liters: string } {
  const cents = toCents(difference);
  if (cents === 0) return { kind: "none", liters: "0.00" };
  return {
    kind: cents < 0 ? "faltante" : "excedente",
    liters: (Math.abs(cents) / 100).toFixed(2),
  };
}

/** Expiry month/year -> `yyyy-mm-01` (stored as the 1st of the month, OPEN-4). */
export function expiryFromParts(month: string | null, year: string | null): string | null {
  if (!month || !year) return null;
  return `${year}-${month.padStart(2, "0")}-01`;
}

export function expiryParts(isoDate: string | null): { month: string | null; year: string | null } {
  if (!isoDate) return { month: null, year: null };
  const [year, month] = isoDate.split("-");
  return { month, year };
}

/** Year choices for the expiry picker: last year to ten years ahead. */
export function expiryYears(today: string): string[] {
  const current = Number(today.slice(0, 4));
  return Array.from({ length: 12 }, (_, i) => String(current - 1 + i));
}

/** Progress 0-100 of actual vs planned liters (machine board). */
export function progressPercent(actual: string | null, planned: string): number {
  const p = toCents(planned);
  if (!p || actual === null) return 0;
  return Math.min(100, Math.round((toCents(actual) / p) * 100));
}
