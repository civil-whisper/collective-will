import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import AnalyticsPage from "../app/[locale]/analytics/page";

function mockFetchWith(data: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    }),
  );
}

describe("AnalyticsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading", async () => {
    mockFetchWith([]);
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Clusters");
  });

  it("shows empty state when no clusters", async () => {
    mockFetchWith([]);
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getByText("No clusters have been created yet.")).toBeTruthy();
  });

  it("displays cluster list with details", async () => {
    mockFetchWith([
      {
        id: "c1",
        summary: "Economic reform",
        domain: "economy",
        member_count: 12,
        approval_count: 8,
        variance_flag: false,
      },
    ]);
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getByText("Economic reform")).toBeTruthy();
    expect(screen.getByText(/economy/)).toBeTruthy();
    expect(screen.getByText(/12/)).toBeTruthy();
    expect(screen.getByText(/8/)).toBeTruthy();
  });

  it("links each cluster to its detail page", async () => {
    mockFetchWith([
      {id: "c1", summary: "Reform A", domain: "economy", member_count: 5, approval_count: 3, variance_flag: false},
    ]);
    const jsx = await AnalyticsPage();
    render(jsx);
    const link = screen.getByRole("link", {name: /Reform A/});
    expect(link.getAttribute("href")).toBe("/en/analytics/clusters/c1");
  });

  it("shows variance flag when set", async () => {
    mockFetchWith([
      {id: "c1", summary: "Unstable cluster", domain: "rights", member_count: 3, approval_count: 1, variance_flag: true},
    ]);
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getAllByText(/Unstable/).length).toBeGreaterThanOrEqual(1);
  });

  it("does not show variance flag when not set", async () => {
    mockFetchWith([
      {id: "c1", summary: "Stable cluster", domain: "rights", member_count: 3, approval_count: 1, variance_flag: false},
    ]);
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.queryByText(/Unstable/)).toBeNull();
  });

  it("renders multiple clusters", async () => {
    mockFetchWith([
      {id: "c1", summary: "Cluster A", domain: "economy", member_count: 5, approval_count: 3, variance_flag: false},
      {id: "c2", summary: "Cluster B", domain: "rights", member_count: 8, approval_count: 6, variance_flag: false},
    ]);
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getAllByRole("listitem").length).toBe(2);
    expect(screen.getByText("Cluster A")).toBeTruthy();
    expect(screen.getByText("Cluster B")).toBeTruthy();
  });

  it("has navigation links to top-policies and evidence", async () => {
    mockFetchWith([]);
    const jsx = await AnalyticsPage();
    render(jsx);
    const topLink = screen.getByRole("link", {name: /Top Policies/});
    expect(topLink.getAttribute("href")).toBe("/en/analytics/top-policies");
    const evidenceLink = screen.getByRole("link", {name: /Evidence Chain/});
    expect(evidenceLink.getAttribute("href")).toBe("/en/analytics/evidence");
  });

  it("handles API failure gracefully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getByText("No clusters have been created yet.")).toBeTruthy();
  });
});
