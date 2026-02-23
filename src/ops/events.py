from __future__ import annotations

import logging
import re
from collections import deque
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal, TypedDict
from uuid import uuid4

EventLevel = Literal["info", "warning", "error"]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SENSITIVE_KEYWORDS = {
    "email",
    "token",
    "password",
    "secret",
    "api_key",
    "authorization",
    "chat_id",
    "wa_id",
    "platform_id",
    "phone",
}
REDACTED = "[REDACTED]"
CORRELATION_ID_HEADER = "x-request-id"
_correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class OpsEvent(TypedDict):
    timestamp: str
    level: EventLevel
    component: str
    event_type: str
    message: str
    correlation_id: str | None
    payload: dict[str, Any]


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(keyword in lower for keyword in SENSITIVE_KEYWORDS)


def redact_text(value: str) -> str:
    return EMAIL_RE.sub(REDACTED, value)


def sanitize_value(value: Any, key_hint: str | None = None) -> Any:
    if key_hint and _is_sensitive_key(key_hint):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, nested in value.items():
            clean[key] = sanitize_value(nested, key)
        return clean
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    return value


def get_correlation_id() -> str | None:
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> Token[str | None]:
    return _correlation_id_ctx.set(correlation_id)


def reset_correlation_id(token: Token[str | None]) -> None:
    _correlation_id_ctx.reset(token)


def new_correlation_id() -> str:
    return uuid4().hex


class OpsEventBuffer:
    def __init__(self, max_size: int = 500) -> None:
        self._events: deque[OpsEvent] = deque(maxlen=max_size)
        self._lock = Lock()

    def add(self, event: OpsEvent) -> None:
        with self._lock:
            self._events.append(event)

    def recent(
        self,
        *,
        limit: int,
        level: EventLevel | None = None,
        event_type: str | None = None,
    ) -> list[OpsEvent]:
        with self._lock:
            items = list(self._events)
        filtered = [
            item
            for item in items
            if (level is None or item["level"] == level)
            and (event_type is None or event_type in item["event_type"])
        ]
        return list(reversed(filtered[-limit:]))


ops_event_buffer = OpsEventBuffer()


class OpsEventHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        level_name = record.levelname.lower()
        level: EventLevel = "info"
        if level_name in {"warning", "error", "critical"}:
            level = "warning" if level_name == "warning" else "error"

        raw_payload = getattr(record, "ops_payload", {})
        payload = sanitize_value(raw_payload)
        if not isinstance(payload, dict):
            payload = {"value": payload}

        ops_event_buffer.add(
            {
                "timestamp": iso_now(),
                "level": level,
                "component": record.name,
                "event_type": str(getattr(record, "event_type", record.name)),
                "message": redact_text(record.getMessage()),
                "correlation_id": getattr(record, "correlation_id", None) or get_correlation_id(),
                "payload": payload,
            }
        )


def configure_ops_event_logging(max_size: int) -> None:
    global ops_event_buffer
    ops_event_buffer = OpsEventBuffer(max_size=max_size)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, OpsEventHandler):
            return

    root_logger.addHandler(OpsEventHandler())
