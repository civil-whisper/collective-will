import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import AnalyticsPage from "../app/[locale]/collective-concerns/page";

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

describe("AnalyticsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading", async () => {
    mockFetchSequence([], {total_voters: 0, total_submissions: 0, pending_submissions: 0, current_cycle: null}, {total: 0, items: []});
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Clusters");
  });

  it("shows empty state when no clusters", async () => {
    mockFetchSequence([], {total_voters: 0, total_submissions: 0, pending_submissions: 0, current_cycle: null}, {total: 0, items: []});
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getByText("No clusters have been created yet.")).toBeTruthy();
  });

  it("displays cluster list with details", async () => {
    mockFetchSequence(
      [
        {
          id: "c1",
          summary: "Economic reform",
          policy_topic: "fiscal-policy",
          policy_key: "fiscal-policy-001",
          member_count: 12,
          approval_count: 8,
          endorsement_count: 5,
        },
      ],
      {total_voters: 10, total_submissions: 5, pending_submissions: 0, current_cycle: null},
      {total: 0, items: []},
    );
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getAllByText("Economic reform").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/fiscal policy/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/12/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/5/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/17/).length).toBeGreaterThanOrEqual(1);
  });

  it("links each cluster to its detail page", async () => {
    mockFetchSequence(
      [{id: "c1", summary: "Reform A", policy_topic: "fiscal-policy", policy_key: "fiscal-policy-001", member_count: 5, approval_count: 3, endorsement_count: 2}],
      {total_voters: 0, total_submissions: 0, pending_submissions: 0, current_cycle: null},
      {total: 0, items: []},
    );
    const jsx = await AnalyticsPage();
    render(jsx);
    const links = screen.getAllByRole("link", {name: /Reform A/});
    expect(links.length).toBeGreaterThanOrEqual(1);
    expect(links[0].getAttribute("href")).toBe("/en/collective-concerns/clusters/c1");
  });

  it("renders multiple clusters", async () => {
    mockFetchSequence(
      [
        {id: "c1", summary: "Cluster A", policy_topic: "fiscal-policy", policy_key: "fiscal-policy-001", member_count: 5, approval_count: 3, endorsement_count: 1},
        {id: "c2", summary: "Cluster B", policy_topic: "civil-rights", policy_key: "civil-rights-001", member_count: 8, approval_count: 6, endorsement_count: 4},
      ],
      {total_voters: 0, total_submissions: 0, pending_submissions: 0, current_cycle: null},
      {total: 0, items: []},
    );
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getAllByText("Cluster A").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Cluster B").length).toBeGreaterThanOrEqual(1);
  });

  it("has navigation links to top-policies and evidence", async () => {
    mockFetchSequence([], {total_voters: 0, total_submissions: 0, pending_submissions: 0, current_cycle: null}, {total: 0, items: []});
    const jsx = await AnalyticsPage();
    render(jsx);
    const topLink = screen.getByRole("link", {name: /Top Policies/});
    expect(topLink.getAttribute("href")).toBe("/en/collective-concerns/top-policies");
    const evidenceLink = screen.getByRole("link", {name: /Evidence Chain/});
    expect(evidenceLink.getAttribute("href")).toBe("/en/collective-concerns/evidence");
  });

  it("shows pending-processing notice and unclustered candidates", async () => {
    mockFetchSequence(
      [],
      {total_voters: 0, total_submissions: 1, pending_submissions: 1, current_cycle: null},
      {
        total: 1,
        items: [
          {
            id: "u1",
            title: "Public transport access",
            summary: "Improve access in underserved areas.",
            policy_topic: "fiscal-policy",
            policy_key: "fiscal-policy-010",
            confidence: 0.81,
          },
        ],
      },
    );
    const jsx = await AnalyticsPage();
    render(jsx);
    expect(screen.getByText(/pending ai processing/i)).toBeTruthy();
    expect(screen.getByText("Public transport access")).toBeTruthy();
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
