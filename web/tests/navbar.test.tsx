import React from "react";
import {render, screen, fireEvent} from "@testing-library/react";
import {afterEach, describe, expect, it} from "vitest";

import {NavBar} from "../components/NavBar";

describe("NavBar", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_OPS_CONSOLE_SHOW_IN_NAV;
  });

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
    expect(hrefs).toContain("/en/signup");
  });

  it("renders signup button", () => {
    render(<NavBar />);
    const signupLinks = screen.getAllByText("Sign Up");
    expect(signupLinks.length).toBeGreaterThanOrEqual(1);
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

  it("renders Ops link when flag is enabled", () => {
    process.env.NEXT_PUBLIC_OPS_CONSOLE_SHOW_IN_NAV = "true";
    render(<NavBar />);
    expect(screen.getByText("Ops")).toBeTruthy();
  });

  it("renders the language switcher buttons", () => {
    render(<NavBar />);
    expect(screen.getAllByLabelText("English").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByLabelText("فارسی").length).toBeGreaterThanOrEqual(1);
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
