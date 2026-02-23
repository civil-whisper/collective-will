from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.request_context import RequestContextMiddleware
from src.api.routes import api_router
from src.config import get_settings
from src.db.connection import check_db_health
from src.ops.events import configure_ops_event_logging

settings = get_settings()
configure_ops_event_logging(max_size=settings.ops_event_buffer_size)

app = FastAPI(title="Collective Will", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
