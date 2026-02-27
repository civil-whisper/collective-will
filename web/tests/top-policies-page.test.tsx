import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import CommunityVotesPage from "../app/[locale]/collective-concerns/community-votes/page";

function mockFetchWith(...responses: unknown[]) {
  const fn = vi.fn();
  for (const data of responses) {
    fn.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(data),
    });
  }
  vi.stubGlobal("fetch", fn);
}

const noStats = {
  total_voters: 0,
  total_submissions: 0,
  pending_submissions: 0,
  current_cycle: null,
  active_cycle: null,
};

describe("CommunityVotesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading", async () => {
    mockFetchWith([], noStats);
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Community Votes");
  });

  it("shows empty state when no votes and no active cycle", async () => {
    mockFetchWith([], noStats);
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/No voting cycles have started yet/)).toBeTruthy();
  });

  it("displays ranked policies with rank numbers", async () => {
    mockFetchWith(
      [
        {cluster_id: "c1", summary: "Policy Alpha", approval_count: 20, approval_rate: 0.85, policy_topic: "fiscal-policy"},
        {cluster_id: "c2", summary: "Policy Beta", approval_count: 15, approval_rate: 0.72},
      ],
      noStats,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("2").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Policy Alpha")).toBeTruthy();
    expect(screen.getByText("Policy Beta")).toBeTruthy();
  });

  it("links each policy to its cluster detail page", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Policy Alpha", approval_count: 20, approval_rate: 0.85}],
      noStats,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    const link = screen.getByRole("link", {name: /Policy Alpha/});
    expect(link.getAttribute("href")).toBe("/en/collective-concerns/clusters/c1");
  });

  it("shows approval rate as percentage", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Test", approval_count: 10, approval_rate: 0.934}],
      noStats,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/93%/)).toBeTruthy();
  });

  it("shows approval count", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Test", approval_count: 42, approval_rate: 0.5}],
      noStats,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/42/)).toBeTruthy();
  });

  it("shows policy_topic when present", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Test", approval_count: 10, approval_rate: 0.5, policy_topic: "governance-reform"}],
      noStats,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/governance reform/)).toBeTruthy();
  });

  it("falls back to cluster_id when no summary", async () => {
    mockFetchWith(
      [{cluster_id: "c-uuid-123", approval_count: 10, approval_rate: 0.5}],
      noStats,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByRole("link", {name: /c-uuid-123/})).toBeTruthy();
  });

  it("handles API failure gracefully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/No voting cycles have started yet/)).toBeTruthy();
  });

  it("shows active cycle banner when a cycle is active", async () => {
    mockFetchWith([], {
      ...noStats,
      active_cycle: {
        id: "cycle-1",
        started_at: "2026-02-25T10:00:00Z",
        ends_at: "2026-02-27T10:00:00Z",
        cluster_count: 3,
      },
    });
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/3 policies on the ballot/)).toBeTruthy();
  });

  it("shows Voting Results heading when results exist", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Test", approval_count: 10, approval_rate: 0.5}],
      noStats,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText("Voting Results")).toBeTruthy();
  });
});
