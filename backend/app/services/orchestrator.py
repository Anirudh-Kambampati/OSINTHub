"""Investigation pipeline:

    classify -> plan connector runs -> phase 1 (seed) -> phase 2 (website pivots)
             -> phase 3 (document pivots) -> resolve entities -> score -> final status

Each connector run is isolated: a failure is recorded on its ConnectorRun and the
investigation continues. Runs execute as in-process asyncio tasks behind `JobRunner`;
swap that class for a real queue (arq/Celery) without touching the pipeline.
"""

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.connectors.base import Connector, ConnectorContext, ConnectorError, ConnectorResult, Pivot
from app.core.classify import Classification
from app.core.enums import DEGRADED_RUN_STATUSES, InvestigationStatus, RunStatus, SeedType
from app.core.net import AccessRecord, HostLimiter, SourceHttp, UnsafeURLError
from app.core.normalize import normalize_url
from app.models import AccessLog, ConnectorRun, Investigation
from app.services.resolution import ensure_subject, run_resolution
from app.services.store import persist_findings

log = logging.getLogger("osint.orchestrator")


def plan_runs(investigation_id: str, seed: Classification, connectors: Mapping[str, Connector]) -> list[ConnectorRun]:
    runs = []
    for c in connectors.values():
        for target in c.targets(seed):
            runs.append(ConnectorRun(
                investigation_id=investigation_id, connector=c.name, target=target, phase=1,
                status=RunStatus.PENDING.value, manual_url=c.manual_url(target, seed.type),
            ))
    return runs


class Orchestrator:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        client: httpx.AsyncClient,
        settings: Settings,
        connectors: Mapping[str, Connector],
        limiter: HostLimiter | None = None,
    ) -> None:
        self.sessions = sessions
        self.client = client
        self.settings = settings
        self.connectors = connectors
        self.limiter = limiter or HostLimiter()

    async def execute(self, investigation_id: str) -> None:
        write_lock = asyncio.Lock()  # serialize DB writes per investigation (SQLite-friendly, avoids upsert races)
        try:
            async with self.sessions() as s:
                inv = await s.get(Investigation, investigation_id)
                inv.status = InvestigationStatus.RUNNING.value
                inv.started_at = datetime.now(UTC)
                inv.error = None
                await ensure_subject(s, inv)
                seed = Classification(SeedType(inv.seed_type), inv.seed_normalized)
                pending = (await s.scalars(select(ConnectorRun).where(
                    ConnectorRun.investigation_id == investigation_id,
                    ConnectorRun.status == RunStatus.PENDING.value,
                ))).all()
                await s.commit()

            phase1 = [(r.id, r.connector, r.target, seed.type) for r in pending]
            pivots = await self._run_phase(investigation_id, phase1, write_lock)

            done_targets = {normalize_url(t) for _, _, t, _ in phase1 if "." in t}
            websites = self._select_pivots(pivots, "website", self.settings.max_pivot_websites, done_targets)
            phase2 = await self._create_runs(investigation_id, websites, "website", 2)
            pivots = await self._run_phase(investigation_id, phase2, write_lock)

            documents = self._select_pivots(pivots, "document", self.settings.max_documents, set())
            phase3 = await self._create_runs(investigation_id, documents, "document", 3)
            await self._run_phase(investigation_id, phase3, write_lock)

            async with self.sessions() as s:
                inv = await s.get(Investigation, investigation_id)
                await run_resolution(s, inv)
                statuses = set((await s.scalars(select(ConnectorRun.status).where(
                    ConnectorRun.investigation_id == investigation_id))).all())
                degraded = any(RunStatus(st) in DEGRADED_RUN_STATUSES for st in statuses)
                inv.status = (InvestigationStatus.PARTIAL if degraded else InvestigationStatus.COMPLETED).value
                inv.completed_at = datetime.now(UTC)
                await s.commit()
        except Exception as exc:  # the pipeline itself failed (not a connector)
            log.exception("investigation %s failed", investigation_id)
            async with self.sessions() as s:
                await s.execute(update(ConnectorRun).where(
                    ConnectorRun.investigation_id == investigation_id,
                    ConnectorRun.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value]),
                ).values(status=RunStatus.ERROR.value, message="Investigation pipeline aborted."))
                inv = await s.get(Investigation, investigation_id)
                if inv:
                    inv.status = InvestigationStatus.FAILED.value
                    inv.error = f"{type(exc).__name__}: {exc}"[:1000]
                    inv.completed_at = datetime.now(UTC)
                await s.commit()

    def _select_pivots(self, pivots: list[Pivot], kind: str, limit: int, exclude: set[str]) -> list[str]:
        counts: dict[str, int] = {}
        original: dict[str, str] = {}
        for p in pivots:
            if p.kind != kind:
                continue
            key = normalize_url(p.value)
            if key in exclude:
                continue
            counts[key] = counts.get(key, 0) + 1
            original.setdefault(key, p.value)
        # Websites referenced by several profiles first: they are the most likely to be the subject's own.
        ranked = sorted(counts, key=lambda k: -counts[k])[:limit]
        return [original[k] for k in ranked]

    async def _create_runs(self, investigation_id: str, targets: list[str], pivot_kind: str, phase: int):
        if not targets:
            return []
        out = []
        async with self.sessions() as s:
            for c in self.connectors.values():
                if pivot_kind not in c.accepts_pivots:
                    continue
                for target in targets:
                    run = ConnectorRun(investigation_id=investigation_id, connector=c.name, target=target,
                                       phase=phase, status=RunStatus.PENDING.value)
                    s.add(run)
                    await s.flush()
                    out.append((run.id, c.name, target, SeedType.URL))
            await s.commit()
        return out

    async def _run_phase(self, investigation_id: str, runs, lock: asyncio.Lock) -> list[Pivot]:
        results = await asyncio.gather(*(self._run_one(investigation_id, *r, lock) for r in runs))
        return [p for pivots in results for p in pivots]

    async def _run_one(
        self, investigation_id: str, run_id: str, connector_name: str, target: str, seed_type: SeedType,
        lock: asyncio.Lock,
    ) -> list[Pivot]:
        connector = self.connectors.get(connector_name)
        access: list[AccessRecord] = []
        result: ConnectorResult | None = None
        status, message = RunStatus.ERROR, None

        async with lock, self.sessions() as s:
            await s.execute(update(ConnectorRun).where(ConnectorRun.id == run_id).values(
                status=RunStatus.RUNNING.value, started_at=datetime.now(UTC)))
            await s.commit()

        if connector is None:
            message = f"Connector '{connector_name}' is no longer registered."
        else:
            http = SourceHttp(self.client, self.settings, self.limiter, connector.name, access)
            ctx = ConnectorContext(http=http, settings=self.settings)
            try:
                result = await asyncio.wait_for(
                    connector.run(target, seed_type, ctx), timeout=connector.timeout or self.settings.connector_timeout
                )
                status, message = result.status, result.message
            except ConnectorError as exc:
                status, message = exc.status, str(exc)
            except TimeoutError:
                message = f"{connector.label} did not respond in time."
            except UnsafeURLError as exc:
                message = f"Refused unsafe destination: {exc}"
            except httpx.HTTPError as exc:
                message = f"Network error contacting {connector.label} ({type(exc).__name__})."
            except Exception:  # noqa: BLE001 - one bad connector must never sink the investigation
                log.exception("connector %s crashed on %s", connector_name, target)
                message = f"{connector.label} failed unexpectedly while parsing the response."

        async with lock, self.sessions() as s:
            count = 0
            if result is not None and not result.findings.is_empty:
                try:
                    count = await persist_findings(s, investigation_id, run_id, result.findings)
                except Exception:
                    log.exception("persisting %s findings failed", connector_name)
                    await s.rollback()
                    status, message, result = RunStatus.ERROR, "Results could not be stored.", None
            run = await s.get(ConnectorRun, run_id)
            run.status = RunStatus(status).value
            run.message = message
            run.result_count = count
            run.finished_at = datetime.now(UTC)
            for rec in access:
                s.add(AccessLog(investigation_id=investigation_id, connector=rec.connector, method=rec.method,
                                url=rec.url, status_code=rec.status_code, error=rec.error, at=rec.at))
            await s.commit()
        return result.pivots if result else []


class JobRunner:
    """Bounded in-process background execution. Keeps strong refs so tasks aren't GC'd."""

    def __init__(self, orchestrator: Orchestrator, max_concurrent: int) -> None:
        self.orchestrator = orchestrator
        self._sem = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task] = set()
        self._active: set[str] = set()

    def is_active(self, investigation_id: str) -> bool:
        return investigation_id in self._active

    def submit(self, investigation_id: str) -> None:
        self._active.add(investigation_id)
        task = asyncio.create_task(self._guarded(investigation_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _guarded(self, investigation_id: str) -> None:
        try:
            async with self._sem:
                await self.orchestrator.execute(investigation_id)
        finally:
            self._active.discard(investigation_id)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        for t in self._tasks:
            t.cancel()
        await self.drain()


async def recover_interrupted(sessions: async_sessionmaker[AsyncSession]) -> None:
    """On startup, investigations left running by a previous process are marked partial."""
    async with sessions() as s:
        await s.execute(update(ConnectorRun).where(
            ConnectorRun.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value])
        ).values(status=RunStatus.ERROR.value, message="Interrupted by a server restart."))
        await s.execute(update(Investigation).where(
            Investigation.status.in_([InvestigationStatus.PENDING.value, InvestigationStatus.RUNNING.value])
        ).values(status=InvestigationStatus.PARTIAL.value, error="Interrupted by a server restart."))
        await s.commit()
