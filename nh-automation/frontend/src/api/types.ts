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
