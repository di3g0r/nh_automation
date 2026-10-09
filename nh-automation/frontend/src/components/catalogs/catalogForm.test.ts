import { describe, expect, it } from "vitest";

import { toPayload } from "./catalogForm";
import type { FieldDef } from "./catalogForm";

const fields: FieldDef[] = [
  { name: "code", label: "Código", type: "text", required: true },
  { name: "container_liters", label: "Litros", type: "decimal" },
  { name: "low_stock_threshold", label: "Umbral", type: "int" },
  { name: "site_id", label: "Sitio", type: "select", asNumber: true },
  { name: "in_maintenance", label: "Mant.", type: "checkbox" },
];

describe("toPayload", () => {
  it("trims text, keeps decimals as strings and converts ints/ids to numbers", () => {
    expect(
      toPayload(fields, {
        code: "  M01 ",
        container_liters: "20.5",
        low_stock_threshold: "10",
        site_id: "3",
        in_maintenance: true,
      }),
    ).toEqual({
      code: "M01",
      container_liters: "20.5",
      low_stock_threshold: 10,
      site_id: 3,
      in_maintenance: true,
    });
  });

  it("turns empty optional fields into null so PATCH can clear them", () => {
    const p = toPayload(fields, {
      code: "X",
      container_liters: "  ",
      low_stock_threshold: "",
      site_id: "",
      in_maintenance: false,
    });
    expect(p.container_liters).toBeNull();
    expect(p.low_stock_threshold).toBeNull();
    expect(p.in_maintenance).toBe(false);
  });
});
