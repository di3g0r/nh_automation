import type { Role } from "../api/types";

/** Where each role lands after login (overview §6). */
export function landingPath(role: Role): string {
  if (role === "production_manager") return "/produccion";
  return "/";
}
