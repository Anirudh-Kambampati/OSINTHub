"""Standalone worker process: `python -m app.worker`."""

import asyncio
import signal

import httpx

from app import db
from app.config import get_settings
from app.connectors.registry import CONNECTORS
from app.core.net import HostLimiter
from app.logging_setup import configure_logging
from app.services.orchestrator import Orchestrator
from app.services.worker import Worker


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_json)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    async with httpx.AsyncClient(follow_redirects=False) as client:
        orchestrator = Orchestrator(db.session_factory(), client, settings, CONNECTORS, HostLimiter())
        await Worker(orchestrator, db.session_factory(), settings).run_forever(stop)


if __name__ == "__main__":
    asyncio.run(main())
