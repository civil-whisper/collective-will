from __future__ import annotations

import asyncio
import logging

from src.db.connection import get_sessionmaker
from src.scheduler.main import scheduler_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting pipeline scheduler (6h interval)")
    session_factory = get_sessionmaker()
    asyncio.run(scheduler_loop(session_factory=session_factory, interval_hours=6))


main()
