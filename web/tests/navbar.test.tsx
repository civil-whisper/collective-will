import React from "react";
import {render, screen, fireEvent} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {NavBar} from "../components/NavBar";

describe("NavBar", () => {
  it("renders navigation with all expected links", () => {
    render(<NavBar />);
    const nav = screen.getByRole("navigation");
    expect(nav).toBeTruthy();

    const links = screen.getAllByRole("link");
    const hrefs = links.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/en");
    expect(hrefs).toContain("/en/analytics");
    expect(hrefs).toContain("/en/analytics/top-policies");
    expect(hrefs).toContain("/en/dashboard");
    expect(hrefs).toContain("/en/analytics/evidence");
  });

  it("renders Home link text", () => {
    render(<NavBar />);
    const homeLinks = screen.getAllByText("Home");
    expect(homeLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Analytics link text", () => {
    render(<NavBar />);
    expect(screen.getByText("Analytics")).toBeTruthy();
  });

  it("renders Dashboard link text", () => {
    render(<NavBar />);
    expect(screen.getByText("Dashboard")).toBeTruthy();
  });

  it("renders Audit link text", () => {
    render(<NavBar />);
    expect(screen.getByText("Audit")).toBeTruthy();
  });

  it("renders the language switcher", () => {
    render(<NavBar />);
    expect(screen.getByRole("combobox")).toBeTruthy();
  });

  it("has a mobile menu toggle button", () => {
    render(<NavBar />);
    const toggleBtn = screen.getByLabelText("Toggle menu");
    expect(toggleBtn).toBeTruthy();
    expect(toggleBtn.getAttribute("aria-expanded")).toBe("false");
  });

  it("toggles mobile menu on button click", () => {
    render(<NavBar />);
    const toggleBtn = screen.getByLabelText("Toggle menu");

    fireEvent.click(toggleBtn);
    expect(toggleBtn.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(toggleBtn);
    expect(toggleBtn.getAttribute("aria-expanded")).toBe("false");
  });
});
