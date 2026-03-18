from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.request_context import RequestContextMiddleware
from src.api.routes import api_router
from src.config import get_settings
from src.db.connection import check_db_health
from src.ops.events import configure_ops_event_logging


def _configure_stdout_logging() -> None:
    root_logger = logging.getLogger()
    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler)
        for handler in root_logger.handlers
    )
    if not has_stream_handler:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root_logger.addHandler(handler)
    if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)


settings = get_settings()
_configure_stdout_logging()
configure_ops_event_logging(max_size=settings.ops_event_buffer_size)

app = FastAPI(title="Collective Will", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    if await check_db_health():
        return {"status": "ok"}
    raise HTTPException(status_code=503, detail="database unavailable")
