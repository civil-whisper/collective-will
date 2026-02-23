export const USER_EMAIL_COOKIE = "cw_user_email";
const USER_EMAIL_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export function setUserEmailCookie(email: string): void {
  if (typeof document === "undefined") {
    return;
  }

  document.cookie = [
    `${USER_EMAIL_COOKIE}=${encodeURIComponent(email)}`,
    "Path=/",
    "SameSite=Lax",
    `Max-Age=${USER_EMAIL_COOKIE_MAX_AGE_SECONDS}`,
  ].join("; ");
}
