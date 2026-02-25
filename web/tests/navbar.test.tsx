import React from "react";
import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {NavBar} from "../components/NavBar";

describe("NavBar", () => {
  it("renders navigation with all expected links", () => {
    render(<NavBar showOpsLink={false} />);
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

  it("renders signup button when not logged in", () => {
    render(<NavBar showOpsLink={false} />);
    const signupLinks = screen.getAllByText("Sign Up");
    expect(signupLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("renders user email instead of signup when logged in", () => {
    render(<NavBar showOpsLink={false} userEmail="test@example.com" />);
    expect(screen.getAllByText("test@example.com").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Sign Up")).toBeNull();
  });

  it("renders Home link text", () => {
    render(<NavBar showOpsLink={false} />);
    const homeLinks = screen.getAllByText("Home");
    expect(homeLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Analytics link text", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByText("Analytics").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Dashboard link text", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByText("Dashboard").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Audit link text", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByText("Audit").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Ops link when flag is enabled", () => {
    render(<NavBar showOpsLink />);
    expect(screen.getAllByText("Ops").length).toBeGreaterThanOrEqual(1);
  });

  it("renders the language switcher buttons", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByLabelText("English").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByLabelText("فارسی").length).toBeGreaterThanOrEqual(1);
  });
});
