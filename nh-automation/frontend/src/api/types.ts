/** `operator` is legacy (v3.1): such users cannot log in and are not offered in forms. */
export type Role = "master_admin" | "admin" | "production_manager" | "operator";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
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

export type OrderType = "trabajo" | "retrabajo";

export interface OrderSequence {
  order_type: OrderType;
  prefix: string;
  next_number: number;
  updated_at: string;
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

export interface RazonSocial extends CatalogBase {
  code: string;
  name: string;
}

export interface Product extends CatalogBase {
  code: string;
  name: string;
  provider: string;
  presentation: string;
  container_liters: string | null;
  /** Null only for imported products not yet assigned one. */
  razon_social_id: number | null;
  razon_social_code: string | null;
  razon_social_name: string | null;
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
  has_api_key: boolean; // phase-1 artifact, not shown since phase 4
  plc_db_username: string | null;
  last_seen_at: string | null; // last PLC contact
}

export interface MachineWithKey {
  machine: Machine;
  api_key: string;
}

/** Phase 4: returned once when a PLC login is created or rotated. */
export interface PlcCredentials {
  machine: Machine;
  username: string;
  password: string;
  created: boolean;
  host: string;
  port: number;
  database: string;
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

// Work orders (phase 2) ------------------------------------------------------------

export type ReworkKind = "previous_order" | "own_stock";
export type BarcodeMode = "per_container" | "per_box";
export type OrderStatus =
  "created" | "assigned" | "in_progress" | "paused" | "completed" | "closed" | "cancelled";
export type ChecklistItem = "lote_etiqueta" | "niveles_producto" | "cantidades" | "embalaje";

export interface OrderBaseProduct {
  position: number;
  product_id: number;
  code: string;
  name: string;
  provider: string;
  presentation: string;
  razon_social_code: string;
  liters: string;
}

export interface OrderPackaging {
  packaging_item_id: number;
  code: string;
  description: string;
  planned_qty: number;
  actual_qty: number | null;
  actual_by_name: string | null;
  actual_at: string | null;
}

export interface OrderChecklistEntry {
  item: ChecklistItem;
  checked: boolean;
  checked_by_name: string | null;
  checked_at: string | null;
}

export interface PackagingShortageWarning {
  type: "packaging_shortage";
  packaging_item_id: number;
  code: string;
  description: string;
  planned: number;
  available: number;
}

export interface Order {
  id: number;
  order_type: OrderType;
  sequence: number;
  operation_number: string;
  rework_kind: ReworkKind | null;
  related_order_id: number | null;
  related_operation_number: string | null;
  client_id: number | null;
  client_name: string | null;
  razon_social_id: number;
  razon_social_code: string;
  razon_social_name: string;
  site_id: number;
  site_name: string;
  order_date: string;
  base_products: OrderBaseProduct[];
  base_liters_total: string;
  finished_product_id: number;
  finished_code: string;
  finished_name: string;
  finished_provider: string;
  finished_presentation: string;
  finished_liters: string;
  packaging: OrderPackaging[];
  checklist: OrderChecklistEntry[];
  labels_planned: number | null;
  labels_actual: number | null;
  barcode_mode: BarcodeMode;
  previous_lot: string | null;
  new_lot: string | null;
  expiry_date: string | null;
  expiry_locked: boolean;
  status: OrderStatus;
  warnings: PackagingShortageWarning[];
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  closed_by_name: string | null;
  closed_at: string | null;
  close_note: string | null;
  can_edit: boolean;
  can_cancel: boolean;
  can_delete: boolean;
  // Phase 3 (status-based; the UI also checks permissions).
  can_set_expiry: boolean;
  can_assign: boolean;
  can_edit_traceability: boolean;
  can_close: boolean;
  assignments: Assignment[];
  assigned_liters: string;
  missing_for_assign: MissingForAssign[];
  difference: Difference | null;
  close_missing: MissingForClose[];
  labels_actual_by_name: string | null;
  labels_actual_at: string | null;
  new_lot_by_name: string | null;
  new_lot_at: string | null;
  expiry_set_by_name: string | null;
  expiry_set_at: string | null;
}

export interface OrderListItem {
  id: number;
  order_type: OrderType;
  operation_number: string;
  rework_kind: ReworkKind | null;
  status: OrderStatus;
  order_date: string;
  client_name: string | null;
  razon_social_code: string;
  site_name: string;
  base_products: string[];
  finished_code: string;
  finished_name: string;
  finished_liters: string;
  has_warnings: boolean;
  created_at: string;
}

export interface OrderPayload {
  order_type?: OrderType;
  rework_kind?: ReworkKind | null;
  related_order_id?: number | null;
  client_id?: number | null;
  site_id?: number | null;
  order_date?: string | null;
  base_products?: { product_id: number; liters: string }[];
  finished_product_id?: number;
  finished_liters?: string | null;
  razon_social_id?: number | null;
  comment?: string | null;
  packaging?: { packaging_item_id: number; planned_qty: number }[];
  labels_planned?: number | null;
  barcode_mode?: BarcodeMode;
  previous_lot?: string | null;
}

export interface OrderComment {
  id: number;
  user_id: number;
  user_name: string;
  text: string;
  created_at: string;
}

export interface OrderHistoryEntry {
  id: number;
  created_at: string;
  user_id: number | null;
  user_name: string | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface OrderPrintData {
  order: Order;
  comments: OrderComment[];
  created: { name: string; at: string };
  assigned: { name: string; at: string } | null;
  closed: { name: string; at: string } | null;
  barcodes: { operation_number: string; finished_code: string };
}

export interface ReservationHolder {
  order_id: number;
  operation_number: string;
  order_type: OrderType;
  status: OrderStatus;
  quantity: string;
  created_at: string;
}

export interface ShortageItem {
  product_id: number;
  code: string;
  name: string;
  required: string;
  on_hand: string;
  reserved: string;
  available: string;
  orders: { order_id: number; operation_number: string; quantity: string }[];
}

// Production (phase 3) -----------------------------------------------------------

export type AssignmentStatus = "pending" | "running" | "paused" | "completed" | "cancelled";
export type MachineState = "free" | "busy" | "paused" | "maintenance";
export type MissingForAssign = "expiry" | "machines";
export type MissingForClose = "checklist" | "new_lot" | "materials" | "labels";

export interface Assignment {
  id: number;
  order_id: number;
  operation_number: string;
  order_type: OrderType;
  order_status: OrderStatus;
  finished_code: string;
  finished_name: string;
  machine_id: number;
  machine_code: string;
  machine_name: string;
  planned_liters: string;
  actual_liters: string | null;
  status: AssignmentStatus;
  queue_position: number;
  last_source: "plc" | "manual" | null;
  assigned_by_name: string;
  assigned_at: string;
  started_at: string | null;
  completed_at: string | null;
  can_start: boolean;
  can_pause: boolean;
  can_resume: boolean;
  can_complete: boolean;
  start_blocked_reason: string | null;
}

/** BR-12: negative = Faltante, positive = Excedente. */
export interface Difference {
  ordered_liters: string;
  actual_liters: string;
  difference: string;
  within_range: boolean;
}

export interface ProductionOrder {
  id: number;
  operation_number: string;
  order_type: OrderType;
  status: OrderStatus;
  client_name: string | null;
  razon_social_code: string;
  finished_code: string;
  finished_name: string;
  finished_liters: string;
  expiry_date: string | null;
  created_at: string;
  missing: MissingForAssign[];
  assigned_liters: string;
  assignments: Assignment[];
  difference: Difference | null;
}

export interface MachineBoardItem {
  id: number;
  code: string;
  name: string;
  site_name: string;
  in_maintenance: boolean;
  state: MachineState;
  current: Assignment | null;
  queue_length: number;
  next_assignment: Assignment | null;
  has_plc_login: boolean;
  plc_last_seen_at: string | null;
  plc_last_error: PlcError | null;
}

export interface PlcError {
  error_code: string | null;
  message: string | null;
  received_at: string;
  operation_number: string | null;
}

export interface MachineQueue {
  machine_id: number;
  machine_code: string;
  state: MachineState;
  current: Assignment | null;
  pending: Assignment[];
}
