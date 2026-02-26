import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import TopPoliciesPage from "../app/[locale]/collective-concerns/top-policies/page";

function mockFetchWith(data: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    }),
  );
}

describe("TopPoliciesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading", async () => {
    mockFetchWith([]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Top Policies");
  });

  it("shows empty state when no policies", async () => {
    mockFetchWith([]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByText("No voting cycles completed yet.")).toBeTruthy();
  });

  it("displays ranked policies with rank numbers", async () => {
    mockFetchWith([
      {cluster_id: "c1", summary: "Policy Alpha", approval_count: 20, approval_rate: 0.85, policy_topic: "fiscal-policy"},
      {cluster_id: "c2", summary: "Policy Beta", approval_count: 15, approval_rate: 0.72},
    ]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByText("1")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Policy Alpha")).toBeTruthy();
    expect(screen.getByText("Policy Beta")).toBeTruthy();
  });

  it("links each policy to its cluster detail page", async () => {
    mockFetchWith([
      {cluster_id: "c1", summary: "Policy Alpha", approval_count: 20, approval_rate: 0.85},
    ]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    const link = screen.getByRole("link", {name: /Policy Alpha/});
    expect(link.getAttribute("href")).toBe("/en/collective-concerns/clusters/c1");
  });

  it("shows approval rate as percentage", async () => {
    mockFetchWith([
      {cluster_id: "c1", summary: "Test", approval_count: 10, approval_rate: 0.934},
    ]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByText(/93%/)).toBeTruthy();
  });

  it("shows approval count", async () => {
    mockFetchWith([
      {cluster_id: "c1", summary: "Test", approval_count: 42, approval_rate: 0.5},
    ]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByText(/42/)).toBeTruthy();
  });

  it("shows policy_topic when present", async () => {
    mockFetchWith([
      {cluster_id: "c1", summary: "Test", approval_count: 10, approval_rate: 0.5, policy_topic: "governance-reform"},
    ]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByText(/governance reform/)).toBeTruthy();
  });

  it("falls back to cluster_id when no summary", async () => {
    mockFetchWith([
      {cluster_id: "c-uuid-123", approval_count: 10, approval_rate: 0.5},
    ]);
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByRole("link", {name: /c-uuid-123/})).toBeTruthy();
  });

  it("handles API failure gracefully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    const jsx = await TopPoliciesPage();
    render(jsx);
    expect(screen.getByText("No voting cycles completed yet.")).toBeTruthy();
  });
});
