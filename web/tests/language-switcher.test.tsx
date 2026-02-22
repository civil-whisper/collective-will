import React from "react";
import {render, screen, fireEvent} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";

import {LanguageSwitcher} from "../components/LanguageSwitcher";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({push: mockPush, replace: vi.fn(), back: vi.fn()}),
  usePathname: () => "/en/analytics",
  useSearchParams: () => new URLSearchParams(),
}));

describe("LanguageSwitcher", () => {
  it("renders EN and FA buttons", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByLabelText("English")).toBeTruthy();
    expect(screen.getByLabelText("فارسی")).toBeTruthy();
  });

  it("navigates to Farsi locale on FA button click", () => {
    mockPush.mockClear();
    render(<LanguageSwitcher />);
    fireEvent.click(screen.getByLabelText("فارسی"));
    expect(mockPush).toHaveBeenCalledWith("/fa/analytics");
  });

  it("keeps the path after locale segment when switching", () => {
    mockPush.mockClear();
    render(<LanguageSwitcher />);
    fireEvent.click(screen.getByLabelText("فارسی"));
    const calledPath = mockPush.mock.calls[0][0];
    expect(calledPath).toBe("/fa/analytics");
  });
});
