import { describe, expect, it } from "vitest";

import {
  differenceKind,
  expiryFromParts,
  expiryParts,
  expiryYears,
  progressPercent,
  splitSummary,
} from "./production";

describe("splitSummary", () => {
  it("is exact only when the rows add up to the order liters (BR-7)", () => {
    expect(splitSummary(["70", "30"], "100.00")).toEqual({
      assigned: "100.00",
      remaining: "0.00",
      exact: true,
    });
    expect(splitSummary(["70", "20"], "100.00")).toMatchObject({
      remaining: "10.00",
      exact: false,
    });
    expect(splitSummary(["70", "40"], "100.00")).toMatchObject({
      remaining: "-10.00",
      exact: false,
    });
  });

  it("avoids float error and ignores empty rows", () => {
    expect(splitSummary(["33.33", "33.33", "33.34", ""], "100")).toMatchObject({ exact: true });
    expect(splitSummary([], "100").exact).toBe(false);
  });
});

describe("differenceKind", () => {
  it("labels faltante / excedente with absolute liters", () => {
    expect(differenceKind("-1.00")).toEqual({ kind: "faltante", liters: "1.00" });
    expect(differenceKind("2.50")).toEqual({ kind: "excedente", liters: "2.50" });
    expect(differenceKind("0.00")).toEqual({ kind: "none", liters: "0.00" });
  });
});

describe("expiry helpers", () => {
  it("round-trips month/year as the 1st of the month", () => {
    expect(expiryFromParts("3", "2029")).toBe("2029-03-01");
    expect(expiryFromParts(null, "2029")).toBeNull();
    expect(expiryParts("2029-03-01")).toEqual({ month: "03", year: "2029" });
    expect(expiryParts(null)).toEqual({ month: null, year: null });
  });

  it("offers last year to ten years ahead", () => {
    const years = expiryYears("2026-10-13");
    expect(years[0]).toBe("2025");
    expect(years.at(-1)).toBe("2036");
  });
});

describe("progressPercent", () => {
  it("is capped at 100 and 0 without actual liters", () => {
    expect(progressPercent(null, "70")).toBe(0);
    expect(progressPercent("35", "70")).toBe(50);
    expect(progressPercent("80", "70")).toBe(100);
  });
});
