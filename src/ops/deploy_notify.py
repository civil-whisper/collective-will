"""Send a deploy notification email. Invoked by deploy.sh via Docker."""

from __future__ import annotations

import asyncio
import os
import sys

from src.email.sender import send_operator_email


def main() -> None:
    alert_emails = [e.strip() for e in os.environ.get("OPS_ALERT_EMAILS", "").split(",") if e.strip()]
    resend_key = os.environ.get("RESEND_API_KEY")
    email_from = os.environ.get("EMAIL_FROM", "ops@resend.dev")

    env = os.environ.get("DEPLOY_ENV", "unknown")
    image_tag = os.environ.get("DEPLOY_IMAGE_TAG", "unknown")
    timestamp = os.environ.get("DEPLOY_TIMESTAMP", "unknown")
    services = os.environ.get("DEPLOY_SERVICES_RUNNING", "?/?")
    smoke = os.environ.get("DEPLOY_SMOKE_RESULT", "unknown")

    if not alert_emails or not resend_key:
        print("No alert emails or Resend key configured, skipping.")  # noqa: T201
        sys.exit(0)

    subject = f"[{env.upper()}] Deploy completed — {image_tag}"
    body_text = (
        f"Deploy completed for {env} at {timestamp}.\n\n"
        f"Image: {image_tag}\n"
        f"Services: {services} running\n"
        f"Smoke tests: {smoke}\n\n"
        f"This email confirms the email delivery pipeline is working."
    )

    ok = asyncio.run(
        send_operator_email(
            to=alert_emails,
            subject=subject,
            body_text=body_text,
            resend_api_key=resend_key,
            email_from=email_from,
            http_timeout_seconds=10.0,
        )
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
