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
    mockFetchWith([], noStats, null);
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Community Votes");
  });

  it("shows empty state when no votes and no active cycle", async () => {
    mockFetchWith([], noStats, null);
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
      null,
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
      null,
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
      null,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/93%/)).toBeTruthy();
  });

  it("shows approval count", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Test", approval_count: 42, approval_rate: 0.5}],
      noStats,
      null,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/42/)).toBeTruthy();
  });

  it("shows policy_topic when present", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Test", approval_count: 10, approval_rate: 0.5, policy_topic: "governance-reform"}],
      noStats,
      null,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/governance reform/)).toBeTruthy();
  });

  it("falls back to cluster_id when no summary", async () => {
    mockFetchWith(
      [{cluster_id: "c-uuid-123", approval_count: 10, approval_rate: 0.5}],
      noStats,
      null,
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

  it("shows Past Voting Results heading when results exist", async () => {
    mockFetchWith(
      [{cluster_id: "c1", summary: "Test", approval_count: 10, approval_rate: 0.5}],
      noStats,
      null,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText("Past Voting Results")).toBeTruthy();
  });

  it("shows per-option breakdown bars for archived results", async () => {
    mockFetchWith(
      [{
        cluster_id: "c1",
        summary: "Reform policy",
        approval_count: 8,
        approval_rate: 0.8,
        options: [
          {id: "o1", position: 1, label: "Option Alpha", label_en: "Option Alpha", vote_count: 5},
          {id: "o2", position: 2, label: "Option Beta", label_en: "Option Beta", vote_count: 3},
        ],
      }],
      noStats,
      null,
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText(/Option Alpha/)).toBeTruthy();
    expect(screen.getByText(/Option Beta/)).toBeTruthy();
    expect(screen.getByText(/5\/10/)).toBeTruthy();
    expect(screen.getByText(/3\/10/)).toBeTruthy();
  });

  // --- Active ballot tests ---

  it("shows active ballot section with ballot questions", async () => {
    mockFetchWith(
      [],
      noStats,
      {
        id: "cycle-1",
        started_at: "2026-02-25T10:00:00Z",
        ends_at: "2026-02-27T10:00:00Z",
        total_voters: 5,
        clusters: [
          {
            cluster_id: "c1",
            summary: "Reform governance",
            policy_topic: "governance-reform",
            ballot_question: "Should governance be reformed?",
            ballot_question_fa: null,
            options: [
              {id: "o1", position: 1, label: "Yes", label_en: "Yes", description: "Full reform", description_en: "Full reform"},
              {id: "o2", position: 2, label: "No", label_en: "No", description: "Keep current", description_en: "Keep current"},
            ],
          },
        ],
      },
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText("Active Ballot")).toBeTruthy();
    expect(screen.getByText("Should governance be reformed?")).toBeTruthy();
    expect(screen.getByText(/A\. Yes/)).toBeTruthy();
    expect(screen.getByText(/B\. No/)).toBeTruthy();
    expect(screen.getByText(/5 voters so far/)).toBeTruthy();
    expect(screen.getByText(/Results revealed when voting ends/)).toBeTruthy();
  });

  it("shows option descriptions in active ballot", async () => {
    mockFetchWith(
      [],
      noStats,
      {
        id: "cycle-1",
        started_at: "2026-02-25T10:00:00Z",
        ends_at: "2026-02-27T10:00:00Z",
        total_voters: 0,
        clusters: [
          {
            cluster_id: "c1",
            summary: "Test",
            policy_topic: "test",
            ballot_question: "Test question?",
            ballot_question_fa: null,
            options: [
              {id: "o1", position: 1, label: "Opt1", label_en: "Opt1", description: "Desc for opt1", description_en: "Desc for opt1"},
            ],
          },
        ],
      },
    );
    const jsx = await CommunityVotesPage();
    render(jsx);
    expect(screen.getByText("Desc for opt1")).toBeTruthy();
  });
});
