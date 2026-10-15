import { describe, expect, it } from "vitest";

import {
  changedKeys,
  formatExpiry,
  formatHistoryValue,
  formatPlainDate,
  localToday,
  razonSocialOptions,
  sumLiters,
} from "./orders";

describe("sumLiters", () => {
  it("adds in cents without float error and ignores blanks", () => {
    expect(sumLiters(["0.1", "0.2"])).toBe("0.30");
    expect(sumLiters(["600", "400", ""])).toBe("1000.00");
    expect(sumLiters(["abc"])).toBe("0.00");
  });
});

describe("razonSocialOptions", () => {
  const nb = { razon_social_id: 1, razon_social_code: "NB", razon_social_name: "NOBELTECH" };
  const anb = { razon_social_id: 2, razon_social_code: "ANB", razon_social_name: "AGRONB" };
  it("returns distinct razones sociales in row order, skipping empty rows", () => {
    expect(razonSocialOptions([anb, null, nb, anb]).map((r) => r.code)).toEqual(["ANB", "NB"]);
  });
  it("ignores products without razón social", () => {
    const none = { razon_social_id: null, razon_social_code: null, razon_social_name: null };
    expect(razonSocialOptions([none, nb])).toHaveLength(1);
  });
});

describe("dates", () => {
  it("formats expiry as MM/AAAA and plain dates as dd/mm/aaaa", () => {
    expect(formatExpiry("2029-03-01")).toBe("03/2029");
    expect(formatExpiry(null)).toBe("");
    expect(formatPlainDate("2026-10-05")).toBe("05/10/2026");
  });
  it("uses the local day for today (06:30 UTC is still yesterday in Mazatlán)", () => {
    expect(localToday(new Date("2026-10-14T06:30:00Z"))).toBe("2026-10-13");
    expect(localToday(new Date("2026-10-14T07:30:00Z"))).toBe("2026-10-14");
  });
});

describe("changedKeys", () => {
  it("lists only changed keys, comparing nested values", () => {
    expect(
      changedKeys(
        { a: 1, packaging: [{ id: 1, qty: 5 }], same: "x" },
        { a: 2, packaging: [{ id: 1, qty: 5 }], same: "x", added: true },
      ),
    ).toEqual(["a", "added"]);
    expect(changedKeys(null, { text: "hola" })).toEqual(["text"]);
  });
});

describe("formatHistoryValue", () => {
  it("summarizes snapshot values", () => {
    expect(formatHistoryValue(null)).toBe("—");
    expect(formatHistoryValue([])).toBe("—");
    expect(formatHistoryValue("abc")).toBe("abc");
    expect(
      formatHistoryValue([
        { product_id: 1, code: "BASE-CA", liters: "600.00" },
        { product_id: 2, code: "BASE-K", liters: "400.00" },
      ]),
    ).toBe("BASE-CA 600.00 L, BASE-K 400.00 L");
    expect(
      formatHistoryValue(
        [
          { packaging_item_id: 3, planned_qty: 50 },
          { packaging_item_id: 9, planned_qty: 2 },
        ],
        new Map([[3, "ENVLI20001"]]),
      ),
    ).toBe("ENVLI20001 × 50, #9 × 2");
  });

  it("shows packaging stock corrections as the change in stock", () => {
    expect(
      formatHistoryValue(
        [
          { packaging_item_id: 3, delta: 1 },
          { packaging_item_id: 9, delta: -2 },
        ],
        new Map([[3, "ENVLI20001"]]),
      ),
    ).toBe("ENVLI20001 -1, #9 +2");
  });
});
