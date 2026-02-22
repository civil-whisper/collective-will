import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

import {apiGet, apiPost} from "../lib/api";

describe("apiGet", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({data: "test"}),
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls fetch with correct URL and returns parsed JSON", async () => {
    const result = await apiGet<{data: string}>("/analytics/clusters");
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/analytics/clusters",
      expect.objectContaining({cache: "no-store"}),
    );
    expect(result).toEqual({data: "test"});
  });

  it("forwards extra RequestInit options", async () => {
    await apiGet("/test", {headers: {"X-Custom": "value"}});
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/test",
      expect.objectContaining({
        headers: {"X-Custom": "value"},
        cache: "no-store",
      }),
    );
  });

  it("throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 404, json: () => Promise.resolve({})}),
    );
    await expect(apiGet("/missing")).rejects.toThrow("API request failed: 404");
  });
});

describe("apiPost", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({id: "abc"}),
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends POST with JSON body", async () => {
    const result = await apiPost<{id: string}>("/auth/subscribe", {email: "a@b.com"});
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/auth/subscribe",
      expect.objectContaining({
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({email: "a@b.com"}),
        cache: "no-store",
      }),
    );
    expect(result).toEqual({id: "abc"});
  });

  it("throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    await expect(apiPost("/fail", {})).rejects.toThrow("API request failed: 500");
  });
});
