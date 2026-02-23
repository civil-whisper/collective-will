import {describe, expect, it} from "vitest";

import {resolveServerApiBase} from "../lib/auth-config";

describe("resolveServerApiBase", () => {
  it("prefers BACKEND_API_BASE_URL and trims trailing slash", () => {
    expect(
      resolveServerApiBase({
        BACKEND_API_BASE_URL: "http://backend:8000/",
        NEXT_PUBLIC_API_BASE_URL: "https://example.com/api",
      }),
    ).toBe("http://backend:8000");
  });

  it("uses absolute NEXT_PUBLIC_API_BASE_URL when backend URL is missing", () => {
    expect(
      resolveServerApiBase({
        NEXT_PUBLIC_API_BASE_URL: "https://staging.collectivewill.org/api/",
      }),
    ).toBe("https://staging.collectivewill.org/api");
  });

  it("falls back to localhost when NEXT_PUBLIC_API_BASE_URL is relative", () => {
    expect(
      resolveServerApiBase({
        NEXT_PUBLIC_API_BASE_URL: "/api",
      }),
    ).toBe("http://localhost:8000");
  });
});
