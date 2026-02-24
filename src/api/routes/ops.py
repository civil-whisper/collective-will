from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

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
            sched_detail = heartbeat.detail

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
