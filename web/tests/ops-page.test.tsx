import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

vi.mock("../lib/backend-auth", () => ({
  getBackendAccessToken: vi.fn(async () => "ops-access-token"),
  buildBearerHeaders: vi.fn((token: string) => ({Authorization: `Bearer ${token}`})),
}));

import OpsPage from "../app/[locale]/ops/page";

function mockFetchSequence(...responses: unknown[]) {
  const fn = vi.fn();
  for (const data of responses) {
    fn.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(data),
    });
  }
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("OpsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders health, jobs, and events sections", async () => {
    const fetchMock = mockFetchSequence(
      {
        generated_at: "2026-02-22T10:00:00.000Z",
        require_admin: false,
        services: [
          {name: "api", status: "ok", detail: null},
          {name: "database", status: "ok", detail: null},
        ],
      },
      [
        {
          timestamp: "2026-02-22T10:01:00.000Z",
          level: "info",
          component: "evidence",
          event_type: "submission_received",
          message: "evidence event: submission_received",
          correlation_id: null,
          payload: {},
        },
      ],
      [
        {
          name: "pipeline_batch",
          status: "ok",
          last_run: "2026-02-22T10:00:00.000Z",
          detail: "derived from evidence events",
        },
      ],
    );

    const jsx = await OpsPage({
      searchParams: Promise.resolve({
        cid: "trace-id-ops",
        level: "error",
        type: "api.request.failed",
      }),
    });
    render(jsx);

    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Ops Console");
    expect(screen.getByText("Health")).toBeTruthy();
    expect(screen.getByText("Background Jobs")).toBeTruthy();
    expect(screen.getByText("Recent Events")).toBeTruthy();
    expect(screen.getByText("Quick filters")).toBeTruthy();
    expect(screen.getByText("Failed requests")).toBeTruthy();
    expect(screen.getByText("pipeline_batch")).toBeTruthy();
    expect(screen.getByText("submission_received")).toBeTruthy();
    expect(screen.getByDisplayValue("trace-id-ops")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toContain("correlation_id=trace-id-ops");
    expect(fetchMock.mock.calls[1][0]).toContain("level=error");
    expect(fetchMock.mock.calls[1][0]).toContain("type=api.request.failed");
  });

  it("shows unavailable state when ops endpoint is inaccessible", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 404, json: () => Promise.resolve({})}),
    );

    const jsx = await OpsPage({searchParams: Promise.resolve({})});
    render(jsx);
    expect(screen.getByText(/ops console is disabled/i)).toBeTruthy();
  });

  it("shows filtered empty state with clear action", async () => {
    mockFetchSequence(
      {
        generated_at: "2026-02-22T10:00:00.000Z",
        require_admin: false,
        services: [{name: "api", status: "ok", detail: null}],
      },
      [],
      [],
    );

    const jsx = await OpsPage({searchParams: Promise.resolve({level: "error"})});
    render(jsx);

    expect(screen.getByText("No events match the current filters.")).toBeTruthy();
    const clear = screen.getAllByRole("link", {name: "Clear"}).at(-1);
    expect(clear).toBeTruthy();
    expect(clear?.getAttribute("href")).toBe("/en/ops");
  });
});
