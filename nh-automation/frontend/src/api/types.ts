export type Role = "master_admin" | "admin" | "supervisor" | "operator";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  has_pin: boolean;
  failed_attempts: number;
  locked_until: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Me {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  permissions: string[];
}

export interface Page<T> {
  items: T[];
  total: number;
}

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  entity: string;
  entity_id: number | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export interface Setting {
  key: string;
  value: unknown;
}

/** Builds a `?a=1&b=x` query string, skipping empty values. */
export function toQuery(params: Record<string, string | number | boolean | null | undefined>) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    qs.set(key, String(value));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

// Catalogs (phase 1) -----------------------------------------------------------
// Decimals arrive as strings ("20.00") to avoid float rounding.

interface CatalogBase {
  id: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Site extends CatalogBase {
  name: string;
  is_default: boolean;
}

export interface Client extends CatalogBase {
  name: string;
  code: string;
}

export interface Product extends CatalogBase {
  code: string;
  name: string;
  provider: string;
  presentation: string;
  container_liters: string | null;
}

export type PackagingCategory = "envase" | "caja" | "bolsa" | "etiqueta" | "otro";

export interface PackagingItem extends CatalogBase {
  code: string;
  description: string;
  category: PackagingCategory;
  low_stock_threshold: number;
}

export interface Machine extends CatalogBase {
  code: string;
  name: string;
  site_id: number;
  site_name: string;
  in_maintenance: boolean;
  has_api_key: boolean;
  last_seen_at: string | null;
}

export interface MachineWithKey {
  machine: Machine;
  api_key: string;
}

// Inventory --------------------------------------------------------------------

export type ItemType = "product" | "packaging";
export type MovementType = "receipt" | "adjustment" | "consumption" | "production";

export interface InventoryRow {
  item_type: ItemType;
  item_id: number;
  code: string;
  name: string;
  category: PackagingCategory | null;
  is_active: boolean;
  site_id: number;
  site_name: string;
  on_hand: string;
  reserved: string;
  available: string;
  low_stock_threshold: number | null;
  low_stock: boolean;
  negative: boolean;
}

export interface Availability {
  item_type: ItemType;
  item_id: number;
  site_id: number;
  on_hand: string;
  reserved: string;
  available: string;
}

export interface Movement {
  id: number;
  created_at: string;
  type: MovementType;
  item_type: ItemType;
  item_id: number;
  item_code: string;
  item_name: string;
  site_id: number;
  site_name: string;
  quantity: string;
  order_id: number | null;
  assignment_id: number | null;
  user_id: number | null;
  user_name: string | null;
  note: string | null;
}

export interface MovementUser {
  id: number;
  full_name: string;
}

export interface AlertItem {
  kind: "low_stock" | "negative_stock";
  item_type: ItemType;
  item_id: number;
  code: string;
  name: string;
  site_id: number;
  site_name: string;
  on_hand: string;
  available: string;
  low_stock_threshold: number | null;
}

export interface Alerts {
  low_stock: AlertItem[];
  negative_stock: AlertItem[];
  count: number;
}

// Imports ----------------------------------------------------------------------

export type ImportKind = "products" | "packaging-items";
export type ImportMode = "create_only" | "upsert";
export type ImportAction = "create" | "update" | "skip" | "error";

export interface ImportSource {
  name: string;
  label: string;
  available: boolean;
}

export interface ImportRow {
  row_number: number;
  values: Record<string, string | number | null>;
  action: ImportAction;
  errors: string[];
  warnings: string[];
  apply_initial_stock: boolean;
}

export interface ImportResult {
  kind: ImportKind;
  source: string;
  mode: ImportMode;
  fields: { name: string; label: string; required: boolean }[];
  columns: Record<string, string>;
  unknown_columns: string[];
  missing_columns: string[];
  global_errors: string[];
  summary: Record<"total" | "create" | "update" | "skip" | "error" | "initial_stock", number>;
  has_errors: boolean;
  rows: ImportRow[];
}
