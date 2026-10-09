import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatLiters } from "./datetime";

describe("datetime helpers (America/Mazatlan, UTC-7, no DST)", () => {
  it("converts a UTC 06:30 timestamp to the previous local day", () => {
    // 2026-03-15T06:30:00Z -> 2026-03-14T23:30 local
    expect(formatDate("2026-03-15T06:30:00Z")).toBe("14/03/2026");
  });

  it("formats date and time together as dd/mm/aaaa HH:mm", () => {
    expect(formatDateTime("2026-01-01T12:00:00Z")).toBe("01/01/2026 05:00");
  });

  it("returns an empty string for a missing value", () => {
    expect(formatDateTime(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
  });
});

describe("formatLiters", () => {
  it("formats with thousands separator and 2 decimals", () => {
    expect(formatLiters(1000)).toBe("1,000.00 L");
    expect(formatLiters("250.5")).toBe("250.50 L");
  });
});
