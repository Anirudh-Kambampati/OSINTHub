"""End-to-end pipeline with fake connectors: failures are isolated, results are resolved."""

from sqlalchemy import select

from app.core.classify import classify
from app.core.enums import InvestigationStatus, RunStatus
from app.models import ConnectorRun, Entity, EntityMatch, Investigation, Mention, Observation, Source
from app.services.orchestrator import plan_runs
from app.services.views import list_mentions


async def _create(sessions, connectors, seed="anirudh123") -> str:
    c = classify(seed)
    async with sessions() as s:
        inv = Investigation(seed=seed, seed_normalized=c.normalized, seed_type=c.type.value, title=seed)
        s.add(inv)
        await s.flush()
        s.add_all(plan_runs(inv.id, c, connectors))
        await s.commit()
        return inv.id


async def test_one_failing_connector_does_not_kill_the_investigation(database, orchestrator, connectors):
    iid = await _create(database, connectors)
    await orchestrator.execute(iid)

    async with database() as s:
        inv = await s.get(Investigation, iid)
        runs = {r.connector: r for r in (await s.scalars(select(ConnectorRun))).all()}
        assert inv.status == InvestigationStatus.PARTIAL.value
        assert runs["github"].status == RunStatus.FOUND.value
        assert runs["devto"].status == RunStatus.FOUND.value
        # Not found is distinct from failure, and failures are never turned into "not found".
        assert runs["gitlab"].status == RunStatus.NOT_FOUND.value
        assert runs["broken"].status == RunStatus.ERROR.value
        assert runs["broken"].message == "Upstream exploded"
        assert runs["crashy"].status == RunStatus.ERROR.value
        assert "bug in parser" not in runs["crashy"].message  # internals aren't leaked to the UI


async def test_every_observation_has_a_source(database, orchestrator, connectors):
    iid = await _create(database, connectors)
    await orchestrator.execute(iid)
    async with database() as s:
        observations = (await s.scalars(select(Observation).where(Observation.investigation_id == iid))).all()
        source_ids = set((await s.scalars(select(Source.id))).all())
        assert observations
        assert all(o.source_id in source_ids for o in observations)


async def test_resolution_links_corroborated_profiles(database, orchestrator, connectors):
    iid = await _create(database, connectors)
    await orchestrator.execute(iid)
    async with database() as s:
        matches = (await s.execute(
            select(Entity.key, EntityMatch.score, EntityMatch.label).join(Entity, Entity.id == EntityMatch.entity_id)
        )).all()
        by_key = {k: (score, label) for k, score, label in matches}
        # Same username + same email + github links to devto => strong match.
        assert by_key["github:anirudh123"][0] >= 0.85
        assert by_key["devto:anirudh123"][0] >= 0.60
        inv = await s.get(Investigation, iid)
        assert inv.title == "Anirudh K"  # subject named from corroborated evidence


async def test_rerun_accumulates_observations(database, orchestrator, connectors):
    iid = await _create(database, connectors)
    await orchestrator.execute(iid)
    async with database() as s:
        inv = await s.get(Investigation, iid)
        s.add_all(plan_runs(iid, classify(inv.seed), connectors))
        await s.commit()
    await orchestrator.execute(iid)
    async with database() as s:
        emails = (await s.scalars(select(Observation).where(Observation.attribute == "email"))).all()
        assert len(emails) == 4  # 2 profiles x 2 runs; entities are not duplicated
        profiles = (await s.scalars(select(Entity).where(Entity.kind == "profile"))).all()
        assert len(profiles) == 2


async def test_mention_confidence_is_scaled_by_profile_match(database, orchestrator, connectors):
    iid = await _create(database, connectors)
    await orchestrator.execute(iid)
    async with database() as s:
        devto = await s.scalar(select(Entity).where(Entity.key == "devto:anirudh123"))
        devto.confidence = 0.4  # simulate a weakly matched profile
        src = await s.scalar(select(Source.id).limit(1))
        s.add(Mention(investigation_id=iid, entity_id=devto.id, source_id=src, category="social",
                      url="https://dev.to/a/post", title="Post", association="Authored by profile", confidence=0.95))
        s.add(Mention(investigation_id=iid, source_id=src, category="news", url="https://news.example/x",
                      title="Text hit", association="Text match (unverified)", confidence=0.25))
        await s.commit()
        page = await list_mentions(s, iid, None, "confidence", 10, 0)
        by_url = {m.url: m for m in page.items}
        assert by_url["https://dev.to/a/post"].confidence == round(0.95 * 0.4, 4)
        assert by_url["https://news.example/x"].confidence == 0.25
        assert by_url["https://news.example/x"].level == "low"
