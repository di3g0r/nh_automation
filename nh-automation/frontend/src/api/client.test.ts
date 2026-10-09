import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status,
      ok: status >= 200 && status < 300,
      json: async () => body,
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "";
});

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    mockFetch(200, { username: "jdoe" });
    const result = await api.get<{ username: string }>("/auth/me");
    expect(result.username).toBe("jdoe");
  });

  it("throws ApiError with the server's code/message on failure", async () => {
    mockFetch(401, {
      error: { code: "INVALID_CREDENTIALS", message: "Usuario o contraseña incorrectos." },
    });

    await expect(api.post("/auth/login", { username: "x", password: "y" })).rejects.toMatchObject({
      status: 401,
      code: "INVALID_CREDENTIALS",
    });
  });

  it("is an instance of ApiError", async () => {
    mockFetch(403, { error: { code: "FORBIDDEN", message: "No tiene permiso." } });
    try {
      await api.get("/users");
      expect.fail("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
    }
  });
});
