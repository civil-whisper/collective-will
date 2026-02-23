import React, {act} from "react";
import {render, screen, fireEvent, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

import EvidencePage from "../app/[locale]/analytics/evidence/page";

const SAMPLE_ENTRIES = [
  {
    id: 1,
    timestamp: "2026-02-20T10:00:00.000Z",
    event_type: "submission_received",
    entity_type: "submission",
    entity_id: "entity-aaa",
    payload: {status: "pending", raw_text: "Concern about roads", language: "fa", hash: "abc"},
    hash: "aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666",
    prev_hash: "genesis",
  },
  {
    id: 2,
    timestamp: "2026-02-20T10:01:00.000Z",
    event_type: "candidate_created",
    entity_type: "submission",
    entity_id: "entity-bbb",
    payload: {title: "Policy X", domain: "governance", confidence: 0.85, model_version: "gpt-4"},
    hash: "bbbb2222cccc3333dddd4444eeee5555ffff6666aaaa1111",
    prev_hash: "aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666",
  },
];

function mockFetchWith(entries: unknown[], total?: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          total: total ?? entries.length,
          page: 1,
          per_page: 50,
          entries,
        }),
    }),
  );
}

describe("EvidencePage", () => {
  beforeEach(() => {
    mockFetchWith(SAMPLE_ENTRIES);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading and verify button", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Evidence Chain");
    expect(screen.getByRole("button", {name: /verify chain/i})).toBeTruthy();
  });

  it("fetches and displays entries on mount", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/submission received/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/candidate/i).length).toBeGreaterThan(0);
    });
  });

  it("displays human-readable event descriptions", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
      expect(screen.getByText(/Policy X/)).toBeTruthy();
    });
  });

  it("shows filter pills", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    expect(screen.getByRole("button", {name: /submissions/i})).toBeTruthy();
    expect(screen.getByRole("button", {name: /policies/i})).toBeTruthy();
    expect(screen.getByRole("button", {name: /votes/i})).toBeTruthy();
  });

  it("filters entries by search term on event description", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, {target: {value: "Policy X"}});

    expect(screen.queryByText(/Concern about roads/)).toBeNull();
    expect(screen.getByText(/Policy X/)).toBeTruthy();
  });

  it("filters entries by search term on entity_id", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, {target: {value: "entity-bbb"}});

    expect(screen.getByText(/Policy X/)).toBeTruthy();
    expect(screen.queryByText(/Concern about roads/)).toBeNull();
  });

  it("shows all entries when search is cleared", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, {target: {value: "entity-aaa"}});
    expect(screen.queryByText(/Policy X/)).toBeNull();

    fireEvent.change(searchInput, {target: {value: ""}});
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
      expect(screen.getByText(/Policy X/)).toBeTruthy();
    });
  });

  it("expands entry details on click", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    const entryButton = screen.getAllByRole("button").find(
      (btn) => btn.textContent?.includes("Concern about roads"),
    )!;
    fireEvent.click(entryButton);

    expect(screen.getByText(/entity-aaa/)).toBeTruthy();
  });

  it("collapses entry details on second click", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    const entryButton = screen.getAllByRole("button").find(
      (btn) => btn.textContent?.includes("Concern about roads"),
    )!;
    fireEvent.click(entryButton);
    expect(screen.getByText(/entity-aaa/)).toBeTruthy();

    fireEvent.click(entryButton);
    await waitFor(() => {
      const entityTexts = screen.queryAllByText("entity-aaa");
      expect(entityTexts.length).toBe(0);
    });
  });

  it("expands entry on Enter keypress", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    const entryButton = screen.getAllByRole("button").find(
      (btn) => btn.textContent?.includes("Concern about roads"),
    )!;
    fireEvent.keyDown(entryButton, {key: "Enter"});

    expect(screen.getByText(/entity-aaa/)).toBeTruthy();
  });

  it("has Previous button disabled on page 1", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    const prevBtn = screen.getByRole("button", {name: /previous/i});
    expect(prevBtn).toBeDisabled();
  });

  it("increments page on Next click and fetches again", async () => {
    mockFetchWith(SAMPLE_ENTRIES, 100);
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(1);
    });
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain("page=1");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /next/i}));
    });

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2);
    });
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[1][0]).toContain("page=2");
  });

  it("does not decrement page below 1", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /previous/i}));
    });
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it("shows chain valid after verify", async () => {
    const fetchMock = vi.fn();
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({total: 1, page: 1, per_page: 50, entries: SAMPLE_ENTRIES}),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({valid: true, entries_checked: 2}),
      });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /verify chain/i}));
    });

    await waitFor(() => {
      expect(screen.getByText(/Chain Valid/i)).toBeTruthy();
    });
  });

  it("shows chain invalid after verify failure", async () => {
    const fetchMock = vi.fn();
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({total: 1, page: 1, per_page: 50, entries: SAMPLE_ENTRIES}),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({valid: false, entries_checked: 1}),
      });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Concern about roads/)).toBeTruthy();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /verify chain/i}));
    });

    await waitFor(() => {
      expect(screen.getByText(/Chain Broken/i)).toBeTruthy();
    });
  });

  it("shows empty list when API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText("0")).toBeTruthy();
    });
  });

  it("shows total entries count from API", async () => {
    mockFetchWith(SAMPLE_ENTRIES, 42);
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText("42")).toBeTruthy();
    });
  });
});
