/**
 * Display helpers for America/Mazatlan (NFR-7a). The API always sends UTC
 * ISO-8601 timestamps; conversion to local time happens only here, at
 * render time, never by mutating stored data.
 */
const LOCAL_TZ = "America/Mazatlan";

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  const datePart = new Intl.DateTimeFormat("es-MX", {
    timeZone: LOCAL_TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
  const timePart = new Intl.DateTimeFormat("es-MX", {
    timeZone: LOCAL_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
  return `${datePart} ${timePart}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("es-MX", {
    timeZone: LOCAL_TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(iso));
}

/** `1,000.00 L` formatting for liter quantities (overview §6). */
export function formatLiters(value: number | string): string {
  const n = typeof value === "string" ? Number(value) : value;
  return `${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} L`;
}
