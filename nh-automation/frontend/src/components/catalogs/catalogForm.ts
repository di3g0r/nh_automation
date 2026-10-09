export type FieldValue = string | boolean;

export interface FieldDef {
  name: string;
  label: string;
  type: "text" | "decimal" | "int" | "select" | "checkbox";
  required?: boolean;
  description?: string;
  options?: { value: string; label: string; disabled?: boolean }[];
  /** Send the (select) value as a number, e.g. foreign-key ids. */
  asNumber?: boolean;
  /** Only shown when creating (e.g. a field managed by its own action afterwards). */
  createOnly?: boolean;
}

/** Form values -> API payload. Empty optional fields become null (clears them). */
export function toPayload(fields: FieldDef[], values: Record<string, FieldValue>) {
  const payload: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.name];
    if (f.type === "checkbox") payload[f.name] = Boolean(v);
    else if (typeof v === "string" && v.trim() === "") payload[f.name] = null;
    else if (f.type === "int" || f.asNumber) payload[f.name] = Number(v);
    else payload[f.name] = typeof v === "string" ? v.trim() : v;
  }
  return payload;
}
