"""Ops monitor: check backend health and send alert/heartbeat emails.

Designed to be invoked by a systemd timer every 5 minutes via
``scripts/monitor-ops.sh`` or ``python -m src.ops.monitor``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from src.email.sender import send_operator_email

logger = logging.getLogger(__name__)

STATE_DIR = Path("/var/lib/collective-will-monitor")
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


def _state_path(env: str) -> Path:
    return STATE_DIR / f"{env}.json"


def _load_state(env: str) -> dict[str, Any]:
    path = _state_path(env)
    if path.exists():
        try:
            data: dict[str, Any] = json.loads(path.read_text())
            return data
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt monitor state at %s, resetting", path)
    return {
        "active_fingerprints": {},
        "last_heartbeat_date": None,
        "last_check_at": None,
    }


def _save_state(env: str, state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(env).write_text(json.dumps(state, indent=2, default=str))


def _fingerprint(service: str, detail: str | None) -> str:
    raw = f"{service}:{detail or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _format_alert_text(env: str, failures: list[dict[str, str]], health: dict[str, Any]) -> str:
    lines = [
        f"[{env.upper()}] Service alert — {len(failures)} issue(s) detected",
        f"Checked at: {health.get('generated_at', 'unknown')}",
        "",
    ]
    for f in failures:
        lines.append(f"  * {f['service']}: {f['status']} — {f['detail']}")
    lines.append("")

    error_count = health.get("recent_error_count", 0)
    warning_count = health.get("recent_warning_count", 0)
    pipeline_count = health.get("pipeline_degradation_count", 0)
    if error_count or warning_count or pipeline_count:
        lines.append(
            f"Recent errors: {error_count}  |  warnings: {warning_count}"
            f"  |  pipeline degradations: {pipeline_count}"
        )

    tg_url = health.get("telegram_webhook_url")
    tg_pending = health.get("telegram_pending_updates")
    tg_error = health.get("telegram_last_error")
    if tg_url or tg_pending or tg_error:
        lines.append("")
        lines.append("Telegram webhook:")
        if tg_url:
            lines.append(f"  URL: {tg_url}")
        if tg_pending is not None:
            lines.append(f"  Pending updates: {tg_pending}")
        if tg_error:
            lines.append(f"  Last error: {tg_error}")

    error_events = health.get("recent_error_events", [])
    if error_events:
        lines.append("")
        lines.append("Recent backend errors:")
        for event in error_events[:3]:
            exception_type = event.get("exception_type")
            suffix = f" ({exception_type})" if exception_type else ""
            lines.append(
                f"  [{event.get('timestamp', 'unknown')}] {event.get('component', 'unknown')}: "
                f"{event.get('message', '')}{suffix}"
            )

    return "\n".join(lines)


def _format_alert_html(env: str, failures: list[dict[str, str]], health: dict[str, Any]) -> str:
    rows = ""
    for f in failures:
        color = "#dc2626" if f["status"] == "error" else "#d97706"
        rows += f'<tr><td style="padding:6px 12px;">{f["service"]}</td>'
        rows += f'<td style="padding:6px 12px;color:{color};font-weight:600;">{f["status"]}</td>'
        rows += f'<td style="padding:6px 12px;">{f["detail"]}</td></tr>'

    error_count = health.get("recent_error_count", 0)
    warning_count = health.get("recent_warning_count", 0)
    pipeline_count = health.get("pipeline_degradation_count", 0)
    error_events = health.get("recent_error_events", [])
    error_event_items = ""
    for event in error_events[:3]:
        exception_type = event.get("exception_type")
        suffix = f" ({exception_type})" if exception_type else ""
        error_event_items += (
            "<li style=\"margin:0 0 8px;\">"
            f"<strong>{event.get('timestamp', 'unknown')}</strong> — "
            f"{event.get('component', 'unknown')}: {event.get('message', '')}{suffix}"
            "</li>"
        )
    error_events_html = ""
    if error_event_items:
        error_events_html = (
            "<h3 style=\"margin:20px 0 8px;font-size:15px;\">Recent backend errors</h3>"
            "<ul style=\"padding-left:18px;margin:0;font-size:13px;line-height:1.5;\">"
            f"{error_event_items}</ul>"
        )

    return f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:20px;font-family:system-ui,sans-serif;background:#f4f4f5;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;padding:24px;">
<h2 style="margin:0 0 12px;color:#dc2626;">⚠ [{env.upper()}] Service Alert</h2>
<p style="color:#6b7280;margin:0 0 16px;">Checked at {health.get('generated_at', 'unknown')}</p>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#f9fafb;"><th style="text-align:left;padding:8px 12px;">Service</th>
<th style="text-align:left;padding:8px 12px;">Status</th>
<th style="text-align:left;padding:8px 12px;">Detail</th></tr>
{rows}
</table>
<p style="margin:16px 0 0;font-size:13px;color:#6b7280;">
Errors: {error_count} &nbsp;|&nbsp; Warnings: {warning_count} &nbsp;|&nbsp; Pipeline degradations: {pipeline_count}
</p>
{error_events_html}
</div></body></html>"""


def _format_heartbeat_text(env: str, health: dict[str, Any]) -> str:
    lines = [
        f"[{env.upper()}] Daily heartbeat — all services OK",
        f"Checked at: {health.get('generated_at', 'unknown')}",
        "",
    ]
    for svc in health.get("services", []):
        lines.append(f"  {svc['name']}: {svc['status']}")
    return "\n".join(lines)


def _format_heartbeat_html(env: str, health: dict[str, Any]) -> str:
    rows = ""
    for svc in health.get("services", []):
        rows += f'<tr><td style="padding:6px 12px;">{svc["name"]}</td>'
        rows += f'<td style="padding:6px 12px;color:#16a34a;font-weight:600;">{svc["status"]}</td></tr>'

    return f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:20px;font-family:system-ui,sans-serif;background:#f4f4f5;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;padding:24px;">
<h2 style="margin:0 0 12px;color:#16a34a;">✓ [{env.upper()}] Daily Heartbeat</h2>
<p style="color:#6b7280;margin:0 0 16px;">Checked at {health.get('generated_at', 'unknown')}</p>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#f9fafb;"><th style="text-align:left;padding:8px 12px;">Service</th>
<th style="text-align:left;padding:8px 12px;">Status</th></tr>
{rows}
</table>
</div></body></html>"""


async def check_and_alert(
    *,
    env: str,
    backend_url: str,
    alert_emails: list[str],
    resend_api_key: str | None,
    email_from: str,
    heartbeat_hour_utc: int,
    dedup_minutes: int,
) -> dict[str, Any]:
    """Run a single health check cycle for one environment.

    Returns a summary dict for logging.
    """
    state = _load_state(env)
    now = datetime.now(UTC)
    result: dict[str, Any] = {"env": env, "checked_at": now.isoformat(), "action": "none"}

    health: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{backend_url.rstrip('/')}/ops/monitor-health")
            resp.raise_for_status()
            health = resp.json()
    except Exception as exc:
        health = {
            "generated_at": now.isoformat(),
            "overall_status": "error",
            "services": [{"name": "api", "status": "error", "detail": f"unreachable: {type(exc).__name__}"}],
            "recent_error_count": 0,
            "recent_warning_count": 0,
            "pipeline_degradation_count": 0,
        }

    failures = [
        {"service": svc["name"], "status": svc["status"], "detail": svc.get("detail") or ""}
        for svc in health.get("services", [])
        if svc["status"] in ("error", "degraded")
    ]

    active_fps = state.get("active_fingerprints", {})
    cutoff = (now - timedelta(minutes=dedup_minutes)).isoformat()

    if failures and alert_emails:
        new_failures = []
        for f in failures:
            fp = _fingerprint(f["service"], f["detail"])
            last_sent = active_fps.get(fp)
            if not last_sent or last_sent < cutoff:
                new_failures.append(f)
                active_fps[fp] = now.isoformat()

        if new_failures:
            subject = f"[{env.upper()}] Alert: {len(new_failures)} service issue(s)"
            text = _format_alert_text(env, new_failures, health)
            html = _format_alert_html(env, new_failures, health)
            sent = await send_operator_email(
                to=alert_emails,
                subject=subject,
                body_text=text,
                body_html=html,
                resend_api_key=resend_api_key,
                email_from=email_from,
                http_timeout_seconds=10.0,
            )
            result["action"] = "alert_sent" if sent else "alert_send_failed"
            result["failures"] = new_failures
        else:
            result["action"] = "alert_suppressed_dedup"
    elif not failures:
        # Clear resolved fingerprints
        active_fps.clear()

        today = now.strftime("%Y-%m-%d")
        last_hb_date = state.get("last_heartbeat_date")
        if (
            alert_emails
            and now.hour >= heartbeat_hour_utc
            and last_hb_date != today
        ):
            subject = f"[{env.upper()}] Daily heartbeat — all OK"
            text = _format_heartbeat_text(env, health)
            html = _format_heartbeat_html(env, health)
            sent = await send_operator_email(
                to=alert_emails,
                subject=subject,
                body_text=text,
                body_html=html,
                resend_api_key=resend_api_key,
                email_from=email_from,
                http_timeout_seconds=10.0,
            )
            if sent:
                state["last_heartbeat_date"] = today
                result["action"] = "heartbeat_sent"
            else:
                result["action"] = "heartbeat_send_failed"
        else:
            result["action"] = "all_ok"

    state["active_fingerprints"] = active_fps
    state["last_check_at"] = now.isoformat()
    _save_state(env, state)
    return result


async def run_monitor(envs: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Run monitor checks for all configured environments.

    ``envs`` maps environment names to backend URLs, e.g.
    ``{"staging": "http://127.0.0.1:8000"}``.
    """
    import os

    if envs is None:
        envs = {}
        staging_url = os.environ.get("MONITOR_STAGING_URL", "")
        prod_url = os.environ.get("MONITOR_PRODUCTION_URL", "")
        if staging_url:
            envs["staging"] = staging_url
        if prod_url:
            envs["production"] = prod_url
        if not envs:
            envs["staging"] = DEFAULT_BACKEND_URL

    alert_emails = [
        e.strip() for e in os.environ.get("OPS_ALERT_EMAILS", "").split(",") if e.strip()
    ]
    resend_api_key = os.environ.get("RESEND_API_KEY")
    email_from = os.environ.get("EMAIL_FROM", "ops@resend.dev")
    heartbeat_hour = int(os.environ.get("OPS_HEARTBEAT_HOUR_UTC", "8"))
    dedup_minutes = int(os.environ.get("OPS_ALERT_DEDUP_MINUTES", "60"))

    results = []
    for env_name, url in envs.items():
        try:
            r = await check_and_alert(
                env=env_name,
                backend_url=url,
                alert_emails=alert_emails,
                resend_api_key=resend_api_key,
                email_from=email_from,
                heartbeat_hour_utc=heartbeat_hour,
                dedup_minutes=dedup_minutes,
            )
            results.append(r)
            logger.info("Monitor [%s]: %s", env_name, r.get("action"))
        except Exception:
            logger.exception("Monitor check failed for %s", env_name)
            results.append({"env": env_name, "action": "check_exception"})

    return results


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    results = asyncio.run(run_monitor())
    for r in results:
        print(json.dumps(r, default=str))  # noqa: T201


if __name__ == "__main__":
    main()
