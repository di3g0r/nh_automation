import { describe, expect, it } from "vitest";

import { landingPath } from "./landing";

describe("landingPath", () => {
  it("sends each role to its start page", () => {
    expect(landingPath("operator")).toBe("/operador");
    expect(landingPath("production_manager")).toBe("/produccion");
    expect(landingPath("admin")).toBe("/");
    expect(landingPath("master_admin")).toBe("/");
  });
});
