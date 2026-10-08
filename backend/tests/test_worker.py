from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.core.classify import classify
from app.models import ConnectorRun, Investigation
from app.services.orchestrator import plan_runs
from app.services.worker import Worker


async def _pending(sessions, connectors, seed="anirudh123", **extra) -> str:
    c = classify(seed)
    async with sessions() as s:
        inv = Investigation(seed=seed, seed_normalized=c.normalized, seed_type=c.type.value, title=seed, **extra)
        s.add(inv)
        await s.flush()
        s.add_all(plan_runs(inv.id, c, connectors))
        await s.commit()
        return inv.id


async def test_only_one_worker_claims_an_investigation(database, orchestrator, connectors):
    iid = await _pending(database, connectors)
    a = Worker(orchestrator, database, get_settings(), "a")
    b = Worker(orchestrator, database, get_settings(), "b")
    assert await a.claim(5) == [iid]
    assert await b.claim(5) == []


async def test_worker_completes_queued_investigation(database, orchestrator, connectors):
    iid = await _pending(database, connectors)
    await Worker(orchestrator, database, get_settings(), "w").run_until_idle()
    async with database() as s:
        inv = await s.get(Investigation, iid)
        assert inv.status == "partial" and inv.worker_id is None and inv.run_count == 1


async def test_stale_investigations_are_requeued_and_finished(database, orchestrator, connectors):
    iid = await _pending(database, connectors, status="running", worker_id="dead",
                         heartbeat_at=datetime.now(UTC) - timedelta(hours=1))
    async with database() as s:
        run = await s.scalar(select(ConnectorRun).where(ConnectorRun.investigation_id == iid))
        run.status = "running"
        await s.commit()
    worker = Worker(orchestrator, database, get_settings(), "w")
    await worker.requeue_stale()
    async with database() as s:
        assert (await s.get(Investigation, iid)).status == "pending"
        statuses = set((await s.scalars(select(ConnectorRun.status).where(ConnectorRun.investigation_id == iid))).all())
        assert statuses == {"pending"}
    await worker.run_until_idle()
    async with database() as s:
        assert (await s.get(Investigation, iid)).status == "partial"


async def test_monitoring_reruns_when_due(database, orchestrator, connectors):
    iid = await _pending(database, connectors, monitor_interval_hours=24)
    worker = Worker(orchestrator, database, get_settings(), "w")
    await worker.run_until_idle()
    async with database() as s:
        inv = await s.get(Investigation, iid)
        assert inv.next_run_at is not None
        inv.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    await worker.run_until_idle()
    async with database() as s:
        inv = await s.get(Investigation, iid)
        assert inv.run_count == 2
        assert inv.previous_completed_at is not None


async def test_retention_deletes_old_investigations(database, orchestrator, connectors, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "retention_days", 30)
    old = await _pending(database, connectors, status="completed", created_at=datetime.now(UTC) - timedelta(days=40))
    fresh = await _pending(database, connectors, status="completed")
    await Worker(orchestrator, database, settings, "w").enforce_retention()
    async with database() as s:
        assert await s.get(Investigation, old) is None
        assert await s.get(Investigation, fresh) is not None
