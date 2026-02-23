import React, {act} from "react";
import {render, screen, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

let mockSearchParams = new URLSearchParams();
const mockSignIn = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({push: vi.fn(), replace: vi.fn(), back: vi.fn()}),
  usePathname: () => "/en/verify",
  useSearchParams: () => mockSearchParams,
}));

vi.mock("next-auth/react", () => ({
  signIn: mockSignIn,
}));

import VerifyPage from "../app/[locale]/verify/page";

describe("VerifyPage", () => {
  beforeEach(() => {
    mockSearchParams = new URLSearchParams();
    mockSignIn.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows error when no token is present", async () => {
    await act(async () => {
      render(<VerifyPage />);
    });
    await waitFor(() => {
      expect(screen.getByRole("heading")).toHaveTextContent("Verification Failed");
    });
    expect(screen.getByText(/this link is invalid/i)).toBeTruthy();
  });

  it("shows loading state initially with a valid token", () => {
    mockSearchParams = new URLSearchParams("token=abc123");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(new Promise(() => {})),
    );
    render(<VerifyPage />);
    expect(screen.getByText("Verifying your email...")).toBeTruthy();
  });

  it("shows success after API verification", async () => {
    mockSearchParams = new URLSearchParams("token=valid-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "verified", email: "user@example.com", web_session_code: "web-code"}),
      }),
    );

    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(screen.getByRole("heading")).toHaveTextContent("Email Verified!");
    });
    expect(mockSignIn).toHaveBeenCalledWith("credentials", {
      email: "user@example.com",
      webSessionCode: "web-code",
      redirect: false,
    });
  });

  it("calls the correct API endpoint with the token", async () => {
    mockSearchParams = new URLSearchParams("token=my-special-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "verified"}),
      }),
    );

    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/auth/verify/my-special-token");
  });

  it("displays linking code when API returns a non-verified status", async () => {
    mockSearchParams = new URLSearchParams("token=valid-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "LINK-XYZ-123"}),
      }),
    );

    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(screen.getByRole("heading")).toHaveTextContent("Email Verified!");
    });
    expect(screen.getByText("LINK-XYZ-123")).toBeTruthy();
    expect(screen.getByText(/send this code to our telegram bot/i)).toBeTruthy();
  });

  it("shows Telegram bot link when linking code is present", async () => {
    mockSearchParams = new URLSearchParams("token=valid-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "LINK-ABC"}),
      }),
    );

    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(screen.getByText("LINK-ABC")).toBeTruthy();
    });
    const botLink = screen.getByText("Open Telegram Bot");
    expect(botLink).toBeTruthy();
    expect(botLink.closest("a")?.getAttribute("href")).toContain("t.me/");
  });

  it("does not display linking code when status is 'verified'", async () => {
    mockSearchParams = new URLSearchParams("token=valid-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "verified"}),
      }),
    );

    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(screen.getByRole("heading")).toHaveTextContent("Email Verified!");
    });
    expect(screen.queryByText(/send this code to our telegram bot/i)).toBeNull();
  });

  it("shows error when API call fails", async () => {
    mockSearchParams = new URLSearchParams("token=bad-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({}),
      }),
    );

    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(screen.getByRole("heading")).toHaveTextContent("Verification Failed");
    });
    expect(screen.getByText(/this link is invalid/i)).toBeTruthy();
  });

  it("shows step indicator with email completed and telegram active on success", async () => {
    mockSearchParams = new URLSearchParams("token=valid-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "CODE123"}),
      }),
    );

    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(screen.getByText("Verify Email")).toBeTruthy();
      expect(screen.getByText("Connect Telegram")).toBeTruthy();
    });
  });

  it("links back to signup on error", async () => {
    await act(async () => {
      render(<VerifyPage />);
    });

    await waitFor(() => {
      expect(screen.getByRole("heading")).toHaveTextContent("Verification Failed");
    });
    const allLinks = screen.getAllByRole("link");
    const signupLink = allLinks.find((el) => el.getAttribute("href")?.includes("/signup"));
    expect(signupLink).toBeTruthy();
  });
});
