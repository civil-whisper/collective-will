from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _to_fa_digits(value: int) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _build_magic_link_html(
    magic_link_url: str,
    locale: str,
    *,
    expiry_minutes: int,
) -> tuple[str, str]:
    if locale == "fa":
        subject = "تأیید ایمیل - اراده جمعی"
        heading = "تأیید ایمیل شما"
        body_text = "برای تأیید ایمیل و ادامه ثبت‌نام، روی دکمه زیر کلیک کنید."
        button_text = "تأیید ایمیل"
        expiry_text = f"این لینک تا {_to_fa_digits(expiry_minutes)} دقیقه معتبر است."
        ignore_text = "اگر شما این درخواست را نداده‌اید، این ایمیل را نادیده بگیرید."
        direction = "rtl"
    else:
        subject = "Verify your email - Collective Will"
        heading = "Verify your email"
        body_text = "Click the button below to verify your email and continue signing up."
        button_text = "Verify Email"
        expiry_text = f"This link expires in {expiry_minutes} minutes."
        ignore_text = "If you didn't request this, you can safely ignore this email."
        direction = "ltr"

    html = f"""\
<!DOCTYPE html>
<html dir="{direction}" lang="{locale}">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:system-ui,-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
        style="background:#ffffff;border-radius:12px;padding:40px;max-width:480px;">
        <tr><td style="text-align:center;">
          <h1 style="margin:0 0 16px;font-size:22px;color:#111827;">{heading}</h1>
          <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#4b5563;">{body_text}</p>
          <a href="{magic_link_url}"
             style="display:inline-block;padding:12px 32px;background-color:#6366f1;color:#ffffff;
                    text-decoration:none;border-radius:8px;font-size:15px;font-weight:600;">
            {button_text}
          </a>
          <p style="margin:24px 0 0;font-size:13px;color:#9ca3af;">{expiry_text}</p>
          <p style="margin:8px 0 0;font-size:12px;color:#d1d5db;">{ignore_text}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return subject, html


def _build_plain_text(magic_link_url: str, locale: str, *, expiry_minutes: int) -> str:
    if locale == "fa":
        return (
            f"تأیید ایمیل - اراده جمعی\n\n"
            f"برای تأیید ایمیل خود روی لینک زیر کلیک کنید:\n{magic_link_url}\n\n"
            f"این لینک تا {_to_fa_digits(expiry_minutes)} دقیقه معتبر است."
        )
    return (
        f"Verify your email - Collective Will\n\n"
        f"Click the link below to verify your email:\n{magic_link_url}\n\n"
        f"This link expires in {expiry_minutes} minutes."
    )


async def send_magic_link_email(
    *,
    to: str,
    magic_link_url: str,
    locale: str = "fa",
    resend_api_key: str | None,
    email_from: str,
    expiry_minutes: int,
    http_timeout_seconds: float,
) -> bool:
    """Send a magic link verification email.

    Returns True if sent successfully (or logged in dev mode), False on failure.
    """
    if not resend_api_key:
        logger.info("Magic link for %s: %s (email sending disabled — no RESEND_API_KEY)", to, magic_link_url)
        return True

    subject, html = _build_magic_link_html(magic_link_url, locale, expiry_minutes=expiry_minutes)
    plain_text = _build_plain_text(magic_link_url, locale, expiry_minutes=expiry_minutes)

    payload = {
        "from": email_from,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": plain_text,
    }

    try:
        async with httpx.AsyncClient(timeout=http_timeout_seconds) as client:
            response = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code >= 400:
            logger.error("Resend API error %d: %s", response.status_code, response.text)
            return False
        logger.info("Magic link email sent to %s (Resend ID: %s)", to, response.json().get("id", "unknown"))
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send magic link email to %s", to)
        return False
