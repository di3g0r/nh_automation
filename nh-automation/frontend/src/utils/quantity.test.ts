import { describe, expect, it } from "vitest";

import { adjustmentDelta, formatQuantity, formatSignedQuantity, formatUnits } from "./quantity";

describe("quantity helpers", () => {
  it("formats products in liters and packaging in units", () => {
    expect(formatQuantity("product", "1000.5")).toBe("1,000.50 L");
    expect(formatQuantity("packaging", "1500.00")).toBe("1,500 u");
    expect(formatUnits(3)).toBe("3 u");
  });

  it("signs movement quantities", () => {
    expect(formatSignedQuantity("product", "-7.50")).toBe("-7.50 L");
    expect(formatSignedQuantity("packaging", "20")).toBe("+20 u");
  });

  it("computes the adjustment delta from the counted quantity", () => {
    expect(adjustmentDelta("92.5", "100.00")).toBe(-7.5);
    expect(adjustmentDelta("0.3", "0.1")).toBe(0.2);
    expect(adjustmentDelta("", "10")).toBeNull();
    expect(adjustmentDelta("abc", "10")).toBeNull();
  });
});
