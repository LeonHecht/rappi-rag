import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("apiFetch", () => {
  it("does not require a Supabase session in demo mode", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "true");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ spaces: ["default"] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { apiFetch } = await import("./useApi");
    const result = await apiFetch("user/spaces");

    expect(result).toEqual({ spaces: ["default"] });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/v1/user/spaces",
      expect.objectContaining({
        headers: {},
      })
    );
  });
});
