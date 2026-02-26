from __future__ import annotations

import asyncio
import logging

from src.config import get_settings
from src.db.connection import get_sessionmaker
from src.scheduler.main import scheduler_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    logger.info(
        "Starting pipeline scheduler (%.2fh max interval, threshold=%d)",
        settings.pipeline_interval_hours,
        settings.batch_threshold,
    )
    session_factory = get_sessionmaker()
    asyncio.run(
        scheduler_loop(
            session_factory=session_factory,
            interval_hours=settings.pipeline_interval_hours,
            min_interval_hours=settings.pipeline_min_interval_hours,
            batch_threshold=settings.batch_threshold,
            poll_seconds=settings.batch_poll_seconds,
        )
    )


main()
