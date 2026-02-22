import React, {act} from "react";
import {render, screen, fireEvent, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

import SignupPage from "../app/[locale]/signup/page";

describe("SignupPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "pending_verification", token: "abc"}),
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the signup form with email input", () => {
    render(<SignupPage />);
    expect(screen.getByRole("heading")).toHaveTextContent("Create Your Account");
    expect(screen.getByLabelText("Email address")).toBeTruthy();
    expect(screen.getByRole("button", {name: "Send Verification Link"})).toBeTruthy();
  });

  it("renders step indicators", () => {
    render(<SignupPage />);
    expect(screen.getByText("Verify Email")).toBeTruthy();
    expect(screen.getByText("Connect Telegram")).toBeTruthy();
  });

  it("shows subtitle about no passwords or phone numbers", () => {
    render(<SignupPage />);
    expect(screen.getByText(/no passwords, no phone numbers/i)).toBeTruthy();
  });

  it("shows info about email and telegram usage", () => {
    render(<SignupPage />);
    expect(screen.getByText(/email is used for verification only/i)).toBeTruthy();
    expect(screen.getByText(/telegram lets you submit concerns/i)).toBeTruthy();
  });

  it("shows email sent confirmation after successful submit", async () => {
    render(<SignupPage />);
    const input = screen.getByLabelText("Email address");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button", {name: "Send Verification Link"}).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Check your email!")).toBeTruthy();
    });
    expect(screen.getByText(/verification link to/i)).toBeTruthy();
  });

  it("sends correct payload to API", async () => {
    render(<SignupPage />);
    const input = screen.getByLabelText("Email address");
    fireEvent.change(input, {target: {value: "test@example.com"}});
    fireEvent.submit(screen.getByRole("button", {name: "Send Verification Link"}).closest("form")!);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
    const [url, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/auth/subscribe");
    const body = JSON.parse(options.body);
    expect(body.email).toBe("test@example.com");
    expect(body.locale).toBe("en");
    expect(body.messaging_account_ref).toMatch(/^web-[0-9a-f-]{36}$/);
  });

  it("shows error message when API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    render(<SignupPage />);
    const input = screen.getByLabelText("Email address");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button", {name: "Send Verification Link"}).closest("form")!);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(screen.getByRole("alert").textContent).toContain("Could not send verification link");
  });

  it("shows rate limited message on 429", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 429, json: () => Promise.resolve({})}),
    );
    render(<SignupPage />);
    const input = screen.getByLabelText("Email address");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button", {name: "Send Verification Link"}).closest("form")!);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(screen.getByRole("alert").textContent).toContain("Too many attempts");
  });

  it("disables button while loading", async () => {
    let resolveFetch!: (value: unknown) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
      ),
    );
    render(<SignupPage />);
    const input = screen.getByLabelText("Email address");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button").closest("form")!);

    await waitFor(() => {
      expect(screen.getByRole("button")).toBeDisabled();
    });
    expect(screen.getByRole("button").textContent).toContain("Sending");

    await act(async () => {
      resolveFetch({ok: true, json: () => Promise.resolve({status: "ok"})});
    });
  });

  it("allows resending after email sent", async () => {
    render(<SignupPage />);
    const input = screen.getByLabelText("Email address");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button", {name: "Send Verification Link"}).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Check your email!")).toBeTruthy();
    });

    const resendBtn = screen.getByText("Resend");
    fireEvent.click(resendBtn);

    await waitFor(() => {
      expect(screen.getByLabelText("Email address")).toBeTruthy();
    });
  });

  it("has a sign-in link for existing users", () => {
    render(<SignupPage />);
    const signInLink = screen.getByText("Sign In");
    expect(signInLink.closest("a")?.getAttribute("href")).toContain("/sign-in");
  });
});
