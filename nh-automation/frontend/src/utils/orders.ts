import type { OrderStatus } from "../api/types";

/** Status badge colors, shared by every order screen (overview §6). */
export const STATUS_COLOR: Record<OrderStatus, string> = {
  created: "blue",
  assigned: "cyan",
  in_progress: "yellow",
  paused: "orange",
  completed: "teal",
  closed: "gray",
  cancelled: "red",
};

/** Liters as a 2-decimal string ("" or invalid -> 0), summed in cents to avoid float error. */
export function sumLiters(values: string[]): string {
  const cents = values.reduce((acc, v) => {
    const n = Number(v);
    return acc + (v.trim() === "" || Number.isNaN(n) ? 0 : Math.round(n * 100));
  }, 0);
  return (cents / 100).toFixed(2);
}

export interface RazonSocialRef {
  id: number;
  code: string;
  name: string;
}

/** Distinct razones sociales of the chosen base products, in row order (BR-22). */
export function razonSocialOptions(
  products: ({
    razon_social_id: number | null;
    razon_social_code: string | null;
    razon_social_name: string | null;
  } | null)[],
): RazonSocialRef[] {
  const seen = new Map<number, RazonSocialRef>();
  for (const p of products) {
    if (!p || p.razon_social_id === null || seen.has(p.razon_social_id)) continue;
    seen.set(p.razon_social_id, {
      id: p.razon_social_id,
      code: p.razon_social_code ?? "",
      name: p.razon_social_name ?? "",
    });
  }
  return [...seen.values()];
}

/** Expiry stored as the 1st of the month, shown MM/AAAA. TODO(OPEN-4): exact format. */
export function formatExpiry(isoDate: string | null | undefined): string {
  if (!isoDate) return "";
  const [year, month] = isoDate.split("-");
  return `${month}/${year}`;
}

/** `yyyy-mm-dd` (a calendar date, no timezone) -> `dd/mm/aaaa`. */
export function formatPlainDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "";
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}

/** Today's local date (America/Mazatlan) as `yyyy-mm-dd`, for the order form default. */
export function localToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Mazatlan",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** Keys whose values differ between two audit snapshots (order history). */
export function changedKeys(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
): string[] {
  const keys = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]);
  return [...keys].filter(
    (k) => JSON.stringify(before?.[k] ?? null) !== JSON.stringify(after?.[k] ?? null),
  );
}

/** One audit-snapshot value as short display text (order history tab). */
export function formatHistoryValue(
  value: unknown,
  packagingCodes: Map<number, string> = new Map(),
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    return value
      .map((v) => {
        if (v && typeof v === "object") {
          const o = v as Record<string, unknown>;
          if ("code" in o && "liters" in o) return `${o.code} ${o.liters} L`;
          if ("machine" in o && "liters" in o) return `${o.machine} ${o.liters} L`;
          if ("packaging_item_id" in o) {
            const id = Number(o.packaging_item_id);
            return `${packagingCodes.get(id) ?? `#${id}`} × ${o.planned_qty}`;
          }
          if ("code" in o) return String(o.code);
        }
        return String(v);
      })
      .join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
