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
  it("renders a select with fa and en options", () => {
    render(<LanguageSwitcher />);
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select).toBeTruthy();
    expect(select.value).toBe("en");
    const options = select.querySelectorAll("option");
    expect(options.length).toBe(2);
    expect(options[0].value).toBe("fa");
    expect(options[1].value).toBe("en");
  });

  it("navigates to Farsi locale on selection change", () => {
    render(<LanguageSwitcher />);
    const select = screen.getByRole("combobox");
    fireEvent.change(select, {target: {value: "fa"}});
    expect(mockPush).toHaveBeenCalledWith("/fa/analytics");
  });

  it("keeps the path after locale segment when switching", () => {
    mockPush.mockClear();
    render(<LanguageSwitcher />);
    const select = screen.getByRole("combobox");
    fireEvent.change(select, {target: {value: "fa"}});
    const calledPath = mockPush.mock.calls[0][0];
    expect(calledPath).toBe("/fa/analytics");
  });
});
