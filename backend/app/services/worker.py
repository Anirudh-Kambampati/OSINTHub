"""Durable, database-backed job queue.

Investigations with status `pending` are the queue. Workers claim one with a conditional
UPDATE (only one worker can win), heartbeat while it runs, and anything whose heartbeat
goes stale (crashed worker, restart) is requeued. The same loop fires monitoring re-runs
and enforces data retention. Works with SQLite (single node) and PostgreSQL (many workers).

Run standalone with `python -m app.worker`, or embedded in the API (`OSINT_RUN_WORKER_IN_API`).
"""

import asyncio
import logging
import os
import socket
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.connectors.registry import CONNECTORS
from app.core.classify import Classification
from app.core.enums import InvestigationStatus, RunStatus, SeedType
from app.models import AccessLog, ConnectorRun, Investigation
from app.services.orchestrator import Orchestrator, plan_runs

log = logging.getLogger("osint.worker")
HEARTBEAT_SECONDS = 15
MAINTENANCE_SECONDS = 3600


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:64]


async def enqueue_rerun(s: AsyncSession, inv: Investigation) -> None:
    """Plan fresh connector runs and put the investigation back on the queue."""
    s.add_all(plan_runs(inv.id, Classification(SeedType(inv.seed_type), inv.seed_normalized), CONNECTORS))
    inv.status = InvestigationStatus.PENDING.value
    inv.next_run_at = None
    inv.updated_at = datetime.now(UTC)


class Worker:
    def __init__(self, orchestrator: Orchestrator, sessions: async_sessionmaker[AsyncSession], settings: Settings,
                 worker_id: str | None = None) -> None:
        self.orchestrator = orchestrator
        self.sessions = sessions
        self.settings = settings
        self.worker_id = worker_id or make_worker_id()
        self._tasks: dict[str, asyncio.Task] = {}
        self._wake = asyncio.Event()
        self._last_maintenance = 0.0

    def wake(self) -> None:
        """Called by the API after enqueueing so in-process workers start immediately."""
        self._wake.set()

    @property
    def active(self) -> set[str]:
        return set(self._tasks)

    async def run_forever(self, stop: asyncio.Event) -> None:
        log.info("worker %s started", self.worker_id)
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:  # never let the loop die
                log.exception("worker tick failed")
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.settings.worker_poll_seconds)
            except TimeoutError:
                pass
        await self.shutdown()

    async def tick(self) -> None:
        await self.requeue_stale()
        await self.schedule_monitors()
        if time.monotonic() - self._last_maintenance > MAINTENANCE_SECONDS:
            self._last_maintenance = time.monotonic()
            await self.enforce_retention()
        free = self.settings.max_concurrent_investigations - len(self._tasks)
        for investigation_id in await self.claim(free):
            self._tasks[investigation_id] = asyncio.create_task(self._execute(investigation_id))

    async def claim(self, limit: int) -> list[str]:
        if limit <= 0:
            return []
        claimed = []
        async with self.sessions() as s:
            candidates = (await s.scalars(
                select(Investigation.id).where(Investigation.status == InvestigationStatus.PENDING.value)
                .order_by(Investigation.updated_at).limit(limit * 3)
            )).all()
            for iid in candidates:
                if len(claimed) >= limit:
                    break
                result = await s.execute(
                    update(Investigation)
                    .where(Investigation.id == iid, Investigation.status == InvestigationStatus.PENDING.value)
                    .values(status=InvestigationStatus.RUNNING.value, worker_id=self.worker_id,
                            heartbeat_at=datetime.now(UTC))
                )
                if result.rowcount == 1:  # we won the race
                    claimed.append(iid)
            await s.commit()
        return claimed

    async def _execute(self, investigation_id: str) -> None:
        beat = asyncio.create_task(self._heartbeat(investigation_id))
        try:
            await self.orchestrator.execute(investigation_id)
        finally:
            beat.cancel()
            self._tasks.pop(investigation_id, None)

    async def _heartbeat(self, investigation_id: str) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            async with self.sessions() as s:
                await s.execute(update(Investigation).where(Investigation.id == investigation_id)
                                .values(heartbeat_at=datetime.now(UTC)))
                await s.commit()

    async def requeue_stale(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.worker_heartbeat_timeout_seconds)
        async with self.sessions() as s:
            stale = (await s.scalars(select(Investigation).where(
                Investigation.status == InvestigationStatus.RUNNING.value,
                (Investigation.heartbeat_at.is_(None)) | (Investigation.heartbeat_at < cutoff),
                Investigation.id.not_in(list(self._tasks) or [""]),
            ))).all()
            for inv in stale:
                log.warning("requeueing stale investigation %s (worker %s)", inv.id, inv.worker_id)
                await s.execute(update(ConnectorRun).where(
                    ConnectorRun.investigation_id == inv.id, ConnectorRun.status == RunStatus.RUNNING.value,
                ).values(status=RunStatus.PENDING.value, started_at=None))
                inv.status = InvestigationStatus.PENDING.value
                inv.worker_id = None
            await s.commit()

    async def schedule_monitors(self) -> None:
        async with self.sessions() as s:
            due = (await s.scalars(select(Investigation).where(
                Investigation.next_run_at.is_not(None), Investigation.next_run_at <= datetime.now(UTC),
                Investigation.status.not_in([InvestigationStatus.PENDING.value, InvestigationStatus.RUNNING.value]),
            ))).all()
            for inv in due:
                log.info("monitoring re-run for %s", inv.id)
                await enqueue_rerun(s, inv)
            await s.commit()

    async def enforce_retention(self) -> None:
        if not self.settings.retention_days:
            return
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.retention_days)
        async with self.sessions() as s:
            old = (await s.scalars(select(Investigation.id).where(
                Investigation.created_at < cutoff,
                Investigation.status.not_in([InvestigationStatus.PENDING.value, InvestigationStatus.RUNNING.value]),
            ))).all()
            if old:
                await s.execute(delete(AccessLog).where(AccessLog.investigation_id.in_(old)))
                await s.execute(delete(Investigation).where(Investigation.id.in_(old)))
                log.info("retention: deleted %d investigations older than %d days", len(old),
                         self.settings.retention_days)
            await s.commit()

    async def drain(self) -> None:
        """Wait for everything currently claimed (used by tests and graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def run_until_idle(self) -> None:
        """Process the queue until nothing is pending (tests)."""
        while True:
            await self.tick()
            if not self._tasks:
                return
            await self.drain()

    async def shutdown(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
