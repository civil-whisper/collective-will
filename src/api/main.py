from __future__ import annotations

from fastapi import FastAPI, HTTPException

from src.api.routes import api_router
from src.db.connection import check_db_health

app = FastAPI(title="Collective Will", version="0.1.0")
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    if await check_db_health():
        return {"status": "ok"}
    raise HTTPException(status_code=503, detail="database unavailable")
