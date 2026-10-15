import type { ItemType } from "../api/types";
import { formatLiters } from "./datetime";

/** Whole packaging units with thousands separator: `1,500 u`. */
export function formatUnits(value: number | string): string {
  const n = typeof value === "string" ? Number(value) : value;
  return `${n.toLocaleString("en-US", { maximumFractionDigits: 0 })} u`;
}

/** Liters for products, units for packaging (overview §6, data model §1). */
export function formatQuantity(itemType: ItemType, value: number | string): string {
  return itemType === "product" ? formatLiters(value) : formatUnits(value);
}

/** Signed variant for movements: `+20.00 L`, `-7.50 L`. */
export function formatSignedQuantity(itemType: ItemType, value: number | string): string {
  const n = typeof value === "string" ? Number(value) : value;
  const formatted = formatQuantity(itemType, Math.abs(n));
  return `${n < 0 ? "-" : "+"}${formatted}`;
}

/** Counted - on hand, rounded to 2 decimals (adjustment preview). */
export function adjustmentDelta(counted: string, onHand: string): number | null {
  if (counted.trim() === "" || Number.isNaN(Number(counted))) return null;
  return Math.round((Number(counted) - Number(onHand)) * 100) / 100;
}
