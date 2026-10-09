import { api } from "./client";
import type { AuditLogEntry, Page } from "./types";

export interface AuditFilters {
  user_id?: number;
  entity?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export const auditApi = {
  list: (filters: AuditFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== "") params.set(k, String(v));
    });
    const qs = params.toString();
    return api.get<Page<AuditLogEntry>>(`/audit${qs ? `?${qs}` : ""}`);
  },
};
