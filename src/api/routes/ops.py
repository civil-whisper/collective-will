from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.authn import resolve_email_from_bearer
from src.config import Settings, get_settings
from src.db.connection import check_db_health, get_db
from src.db.evidence import EvidenceLogEntry, isoformat_z
from src.db.heartbeat import get_heartbeat
from src.ops import events as ops_events
from src.ops.events import EventLevel, OpsEvent

router = APIRouter()


class ServiceStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "error", "unknown"]
    detail: str | None = None


class OpsStatusResponse(BaseModel):
    generated_at: str
    require_admin: bool
    services: list[ServiceStatus]


class MonitorHealthResponse(BaseModel):
    generated_at: str
    overall_status: Literal["ok", "degraded", "error"]
    services: list[ServiceStatus]
    recent_error_count: int
    recent_warning_count: int
    pipeline_degradation_count: int
    telegram_webhook_url: str | None = None
    telegram_pending_updates: int | None = None
    telegram_last_error: str | None = None


class OpsEventResponse(BaseModel):
    timestamp: str
    level: EventLevel
    component: str
    event_type: str
    message: str
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class JobStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "error", "unknown"]
    last_run: str | None = None
    detail: str | None = None


def _require_ops_access(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    if not settings.ops_console_enabled:
        raise HTTPException(status_code=404, detail="ops_console_disabled")
    user_email = resolve_email_from_bearer(authorization=authorization)
    if not settings.ops_console_require_admin:
        return user_email

    admin_emails = set(settings.ops_admin_email_list())
    if user_email.lower() not in admin_emails:
        raise HTTPException(status_code=403, detail="admin access required")
    return user_email


def _evidence_to_event(entry: EvidenceLogEntry) -> OpsEvent:
    return {
        "timestamp": isoformat_z(entry.timestamp),
        "level": "info",
        "component": "evidence",
        "event_type": entry.event_type,
        "message": f"evidence event: {entry.event_type}",
        "correlation_id": None,
        "payload": ops_events.sanitize_value(entry.payload),
    }


@router.get("/status", response_model=OpsStatusResponse)
async def status(
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[str | None, Depends(_require_ops_access)],
    session: AsyncSession = Depends(get_db),
) -> OpsStatusResponse:
    db_ok = await check_db_health()
    telegram_ready = bool(settings.telegram_bot_token)
    email_ready = bool(settings.resend_api_key)

    heartbeat = await get_heartbeat(session)
    if heartbeat is None:
        sched_status: Literal["ok", "degraded", "error", "unknown"] = "unknown"
        sched_detail = "no heartbeat recorded yet"
    else:
        age = datetime.now(UTC) - heartbeat.last_run_at
        expected_interval = max(
            settings.pipeline_interval_hours,
            settings.pipeline_min_interval_hours,
        )
        stale_threshold = timedelta(hours=expected_interval * 2.5)
        if heartbeat.status == "error":
            sched_status = "error"
            sched_detail = heartbeat.detail or "last run had errors"
        elif age > stale_threshold:
            sched_status = "degraded"
            hours_ago = age.total_seconds() / 3600
            sched_detail = f"last heartbeat {hours_ago:.1f}h ago (expected every {expected_interval:.1f}h)"
        else:
            sched_status = "ok"
            sched_detail = heartbeat.detail or "ok"

    services = [
        ServiceStatus(name="api", status="ok"),
        ServiceStatus(name="database", status="ok" if db_ok else "error"),
        ServiceStatus(
            name="telegram_webhook",
            status="ok" if telegram_ready else "degraded",
            detail="token configured" if telegram_ready else "telegram token missing",
        ),
        ServiceStatus(
            name="email_transport",
            status="ok" if email_ready else "degraded",
            detail="resend enabled" if email_ready else "console fallback mode",
        ),
        ServiceStatus(
            name="scheduler",
            status=sched_status,
            detail=sched_detail,
        ),
    ]
    return OpsStatusResponse(
        generated_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        require_admin=settings.ops_console_require_admin,
        services=services,
    )


@router.get("/monitor-health", response_model=MonitorHealthResponse)
async def monitor_health(
    settings: Annotated[Settings, Depends(get_settings)],
    session: AsyncSession = Depends(get_db),
) -> MonitorHealthResponse:
    """Unauthenticated health summary for the external monitoring script."""
    db_ok = await check_db_health()
    email_ready = bool(settings.resend_api_key)

    heartbeat = await get_heartbeat(session)
    if heartbeat is None:
        sched_status: Literal["ok", "degraded", "error", "unknown"] = "unknown"
        sched_detail = "no heartbeat recorded yet"
    else:
        age = datetime.now(UTC) - heartbeat.last_run_at
        expected_interval = max(
            settings.pipeline_interval_hours,
            settings.pipeline_min_interval_hours,
        )
        stale_threshold = timedelta(hours=expected_interval * 2.5)
        if heartbeat.status == "error":
            sched_status = "error"
            sched_detail = heartbeat.detail or "last run had errors"
        elif age > stale_threshold:
            sched_status = "degraded"
            hours_ago = age.total_seconds() / 3600
            sched_detail = f"last heartbeat {hours_ago:.1f}h ago (expected every {expected_interval:.1f}h)"
        else:
            sched_status = "ok"
            sched_detail = heartbeat.detail or "ok"

    # Active Telegram verification via getWebhookInfo
    tg_status: Literal["ok", "degraded", "error", "unknown"] = "unknown"
    tg_detail: str | None = None
    tg_webhook_url: str | None = None
    tg_pending: int | None = None
    tg_last_error: str | None = None

    if settings.telegram_bot_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo"
                )
                resp.raise_for_status()
                info = resp.json().get("result", {})
            tg_webhook_url = info.get("url") or None
            tg_pending = info.get("pending_update_count")
            tg_last_error = info.get("last_error_message") or None

            expected_url = f"{settings.app_public_base_url.rstrip('/')}/api/webhooks/telegram"
            if not tg_webhook_url:
                tg_status = "error"
                tg_detail = "webhook URL not set"
            elif tg_webhook_url != expected_url:
                tg_status = "error"
                tg_detail = f"webhook URL mismatch: {tg_webhook_url}"
            elif tg_last_error:
                tg_status = "error"
                tg_detail = f"telegram error: {tg_last_error}"
            elif tg_pending and tg_pending > 100:
                tg_status = "degraded"
                tg_detail = f"{tg_pending} pending updates"
            else:
                tg_status = "ok"
                tg_detail = "webhook healthy"
        except Exception as exc:
            tg_status = "error"
            tg_detail = f"failed to query Telegram API: {type(exc).__name__}"
    else:
        tg_status = "degraded"
        tg_detail = "telegram token missing"

    # Count recent errors/warnings from ops event buffer
    lookback = settings.ops_monitor_lookback_minutes
    mem_events = ops_events.ops_event_buffer.recent(limit=500)
    cutoff = datetime.now(UTC) - timedelta(minutes=lookback)
    cutoff_iso = cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    recent_errors = sum(1 for e in mem_events if e["level"] == "error" and e["timestamp"] >= cutoff_iso)
    recent_warnings = sum(1 for e in mem_events if e["level"] == "warning" and e["timestamp"] >= cutoff_iso)

    # Pipeline degradation count from evidence (last N minutes)
    since = datetime.now(UTC) - timedelta(minutes=lookback)
    result = await session.execute(
        select(EvidenceLogEntry)
        .where(
            EvidenceLogEntry.event_type.in_(PIPELINE_DEGRADATION_EVENTS),
            EvidenceLogEntry.timestamp >= since,
        )
    )
    pipeline_deg_count = len(list(result.scalars().all()))

    services = [
        ServiceStatus(name="api", status="ok"),
        ServiceStatus(name="database", status="ok" if db_ok else "error",
                       detail=None if db_ok else "database health check failed"),
        ServiceStatus(name="telegram_webhook", status=tg_status, detail=tg_detail),
        ServiceStatus(
            name="email_transport",
            status="ok" if email_ready else "degraded",
            detail="resend enabled" if email_ready else "console fallback mode",
        ),
        ServiceStatus(name="scheduler", status=sched_status, detail=sched_detail),
    ]

    # Derive overall status
    statuses = [s.status for s in services]
    if "error" in statuses:
        overall: Literal["ok", "degraded", "error"] = "error"
    elif "degraded" in statuses or "unknown" in statuses:
        overall = "degraded"
    else:
        overall = "ok"

    return MonitorHealthResponse(
        generated_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        overall_status=overall,
        services=services,
        recent_error_count=recent_errors,
        recent_warning_count=recent_warnings,
        pipeline_degradation_count=pipeline_deg_count,
        telegram_webhook_url=tg_webhook_url,
        telegram_pending_updates=tg_pending,
        telegram_last_error=tg_last_error,
    )


@router.get("/events", response_model=list[OpsEventResponse])
async def events(
    _: Annotated[str | None, Depends(_require_ops_access)],
    session: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    level: EventLevel | None = Query(default=None),
    event_type: str | None = Query(default=None, alias="type"),
    correlation_id: str | None = Query(default=None),
) -> list[OpsEventResponse]:
    memory_events = ops_events.ops_event_buffer.recent(limit=limit, level=level, event_type=event_type)
    evidence_events: list[OpsEvent] = []
    if level in {None, "info"}:
        query_limit = min(limit, 200)
        result = await session.execute(
            select(EvidenceLogEntry).order_by(EvidenceLogEntry.id.desc()).limit(query_limit)
        )
        rows = result.scalars().all()
        for row in rows:
            if event_type and event_type not in row.event_type:
                continue
            evidence_events.append(_evidence_to_event(row))

    merged = sorted([*memory_events, *evidence_events], key=lambda item: item["timestamp"], reverse=True)
    if correlation_id:
        merged = [
            item
            for item in merged
            if item["correlation_id"] and correlation_id in item["correlation_id"]
        ]
    cleaned = []
    for item in merged[:limit]:
        cleaned.append(
            {
                **item,
                "message": ops_events.redact_text(item["message"]),
                "payload": ops_events.sanitize_value(item["payload"]),
            }
        )
    return [OpsEventResponse(**item) for item in cleaned]


PIPELINE_DEGRADATION_EVENTS = {
    "submission_deferred_to_batch",
    "candidate_parse_repaired",
    "normalization_step_failed",
    "ballot_generation_failed",
    "policy_options_fallback_used",
    "dispute_ensemble_member_failed",
}


class PipelineStepHealth(BaseModel):
    step: str
    event_count: int
    latest_at: str | None = None


class PipelineHealthResponse(BaseModel):
    generated_at: str
    total_degradation_events: int
    by_step: list[PipelineStepHealth]
    model_fallback_count: int
    recent_degradations: list[OpsEventResponse]


@router.get("/pipeline-health", response_model=PipelineHealthResponse)
async def pipeline_health(
    _: Annotated[str | None, Depends(_require_ops_access)],
    session: AsyncSession = Depends(get_db),
    hours: int = Query(24, ge=1, le=720),
) -> PipelineHealthResponse:
    """Pipeline reliability overview: degradation events by step + model fallback rate."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    result = await session.execute(
        select(EvidenceLogEntry)
        .where(
            EvidenceLogEntry.event_type.in_(PIPELINE_DEGRADATION_EVENTS),
            EvidenceLogEntry.timestamp >= since,
        )
        .order_by(EvidenceLogEntry.timestamp.desc())
    )
    rows = list(result.scalars().all())

    step_map: dict[str, list[EvidenceLogEntry]] = {}
    for row in rows:
        step_map.setdefault(row.event_type, []).append(row)

    by_step = []
    for event_type in sorted(PIPELINE_DEGRADATION_EVENTS):
        entries = step_map.get(event_type, [])
        by_step.append(PipelineStepHealth(
            step=event_type,
            event_count=len(entries),
            latest_at=isoformat_z(entries[0].timestamp) if entries else None,
        ))

    mem_events = ops_events.ops_event_buffer.recent(limit=500, event_type="llm_fallback_used")
    model_fallback_count = len(mem_events)

    recent_items: list[OpsEventResponse] = []
    for row in rows[:20]:
        recent_items.append(OpsEventResponse(
            timestamp=isoformat_z(row.timestamp),
            level="warning",
            component="pipeline",
            event_type=row.event_type,
            message=f"Pipeline degradation: {row.event_type}",
            correlation_id=None,
            payload=ops_events.sanitize_value(row.payload),
        ))

    return PipelineHealthResponse(
        generated_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        total_degradation_events=len(rows),
        by_step=by_step,
        model_fallback_count=model_fallback_count,
        recent_degradations=recent_items,
    )


@router.get("/jobs", response_model=list[JobStatus])
async def jobs(
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[str | None, Depends(_require_ops_access)],
    session: AsyncSession = Depends(get_db),
) -> list[JobStatus]:
    result = await session.execute(select(EvidenceLogEntry).order_by(EvidenceLogEntry.id.desc()).limit(300))
    rows = result.scalars().all()

    def latest_for(event_types: set[str]) -> str | None:
        for row in rows:
            if row.event_type in event_types:
                return isoformat_z(row.timestamp)
        return None

    pipeline_last = latest_for({"candidate_created", "cluster_created", "cluster_updated"})
    anchor_last = latest_for({"anchor_computed"})
    cycle_last = latest_for({"cycle_opened", "cycle_closed"})

    return [
        JobStatus(
            name="pipeline_batch",
            status="ok" if pipeline_last else "unknown",
            last_run=pipeline_last,
            detail="derived from evidence events",
        ),
        JobStatus(
            name="cycle_management",
            status="ok" if cycle_last else "unknown",
            last_run=cycle_last,
            detail="derived from evidence events",
        ),
        JobStatus(
            name="daily_merkle_anchor",
            status="ok" if anchor_last else "unknown",
            last_run=anchor_last,
            detail="local root is required; external publish is optional",
        ),
        JobStatus(
            name="email_delivery",
            status="ok" if settings.resend_api_key else "degraded",
            detail="resend enabled" if settings.resend_api_key else "console fallback mode",
        ),
    ]
