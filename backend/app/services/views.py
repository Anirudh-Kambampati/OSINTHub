"""Read models. Everything shown in the UI is computed here from stored observations."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import CONNECTORS
from app.core.confidence import IDENTITY_THRESHOLD, MAX_INFERRED, level, noisy_or
from app.core.enums import RELIABILITY_WEIGHT, EntityKind, Reliability, RunStatus, SourceCategory
from app.models import (
    AnalystDecision, ConnectorRun, Entity, EntityMatch, Investigation, Mention, Observation, Relationship, Source,
    TimelineEvent, User,
)
from app.schemas import (
    EntityEvidence, EntityOut, EntityRefOut, EvidenceItem, FactorOut, GraphEdge, GraphNode, GraphOut,
    IdentityAttribute, ImageOut, InvestigationDetail, InvestigationOut, MatchOut, MentionOut, MentionPage,
    ObservationOut, PresenceOut, ProfileView, RelationshipOut, RunOut, SourceOut, Stats, TimelineEventOut,
)

PRESENCE_CATEGORIES = {SourceCategory.SOCIAL.value, SourceCategory.CODE.value, SourceCategory.IDENTITY.value}
IMAGE_ATTRIBUTES = ("avatar", "image")
HIDDEN_IDENTITY_ATTRIBUTES = {"avatar", "image", "linked_account"}
ATTRIBUTE_ORDER = [
    "name", "username", "email", "phone", "website", "organization", "occupation", "location", "bio",
    "registrar", "registered_at", "expires_at", "registry_status", "nameserver", "mail_server", "ip_address",
    "spf", "dmarc", "certificate_issuer", "subdomain_count", "first_archived", "last_archived",
    "title", "description",
]
NON_IDENTITY_KINDS = {EntityKind.REPOSITORY.value, EntityKind.DOCUMENT.value, EntityKind.CERTIFICATE.value}
GRAPH_NODE_LIMIT = 400


def source_out(s: Source) -> SourceOut:
    return SourceOut.model_validate(s)


def ref_out(e: Entity) -> EntityRefOut:
    return EntityRefOut(id=e.id, kind=e.kind, label=e.label, platform=(e.data or {}).get("platform"),
                        confidence=e.confidence)


def match_out(m: EntityMatch | None, decision: AnalystDecision | None = None) -> MatchOut | None:
    if m is None:
        return None
    return MatchOut(score=m.score, level=level(m.score), label=m.label, cluster=m.cluster,
                    factors=[FactorOut(**f) for f in m.factors or []],
                    decision=decision.decision if decision else None, decision_note=decision.note if decision else None)


def entity_out(e: Entity, match: EntityMatch | None = None, avatar_id: str | None = None,
               decision: AnalystDecision | None = None, new_since: datetime | None = None) -> EntityOut:
    return EntityOut(id=e.id, kind=e.kind, key=e.key, label=e.label, confidence=e.confidence,
                     level=level(e.confidence), is_seed=e.is_seed, data=e.data or {},
                     match=match_out(match, decision), avatar_observation_id=avatar_id,
                     is_new=bool(new_since and e.created_at > new_since))


def run_out(r: ConnectorRun) -> RunOut:
    c = CONNECTORS.get(r.connector)
    return RunOut(
        id=r.id, connector=r.connector, label=c.label if c else r.connector,
        category=c.category.value if c else "web", target=r.target, phase=r.phase, status=r.status,
        message=r.message, manual_url=r.manual_url, result_count=r.result_count, started_at=r.started_at,
        finished_at=r.finished_at,
    )


def latest_runs(runs: list[ConnectorRun]) -> list[ConnectorRun]:
    """Re-runs append new ConnectorRuns; views show the most recent per (connector, target)."""
    latest: dict[tuple[str, str], ConnectorRun] = {}
    for r in sorted(runs, key=lambda r: r.created_at):
        latest[(r.connector, r.target)] = r
    return sorted(latest.values(), key=lambda r: (r.phase, r.created_at))


async def _count(s: AsyncSession, model, *where) -> int:
    return await s.scalar(select(func.count()).select_from(model).where(*where)) or 0


async def investigation_stats(s: AsyncSession, inv: Investigation, runs: list[ConnectorRun]) -> Stats:
    iid = inv.id
    matches = (await s.scalars(select(EntityMatch.score).where(EntityMatch.investigation_id == iid))).all()
    kinds = dict((await s.execute(
        select(Entity.kind, func.count()).where(Entity.investigation_id == iid).group_by(Entity.kind)
    )).all())
    current = latest_runs(runs)
    matched = [m for m in matches if m >= IDENTITY_THRESHOLD]
    confidence = await _overall_confidence(s, inv, matched)
    since = inv.previous_completed_at
    new_entities = await _count(s, Entity, Entity.investigation_id == iid, Entity.created_at > since) if since else 0
    new_mentions = await _count(s, Mention, Mention.investigation_id == iid, Mention.observed_at > since) if since else 0
    return Stats(
        new_entities=new_entities,
        new_mentions=new_mentions,
        profiles=kinds.get(EntityKind.PROFILE.value, 0),
        matched_profiles=len(matched),
        mentions=await _count(s, Mention, Mention.investigation_id == iid),
        sources=await _count(s, Source, Source.investigation_id == iid),
        relationships=await _count(s, Relationship, Relationship.investigation_id == iid),
        documents=kinds.get(EntityKind.DOCUMENT.value, 0),
        domains=kinds.get(EntityKind.DOMAIN.value, 0),
        entities=sum(kinds.values()),
        connectors_run=sum(1 for r in current if r.status not in (RunStatus.PENDING, RunStatus.RUNNING)),
        connectors_total=len(current),
        confidence=confidence,
        level=level(confidence) if confidence is not None else None,
    )


async def _overall_confidence(s: AsyncSession, inv: Investigation, matched: list[float]) -> float | None:
    """Person-like subjects: mean match score of the profiles that make up the identity.
    Domain/URL subjects: mean confidence of the strongest directly observed attributes."""
    if matched:
        return round(sum(matched) / len(matched), 4)
    seed = await s.scalar(select(Entity).where(Entity.investigation_id == inv.id, Entity.is_seed.is_(True)))
    if seed is None:
        return None
    confs = sorted((await s.scalars(select(Observation.confidence).where(Observation.entity_id == seed.id))).all(),
                   reverse=True)[:5]
    return round(sum(confs) / len(confs), 4) if confs else None


async def investigation_out(s: AsyncSession, inv: Investigation, *, with_runs: bool) -> InvestigationOut:
    runs = (await s.scalars(select(ConnectorRun).where(ConnectorRun.investigation_id == inv.id))).all()
    owner = await s.get(User, inv.owner_id) if inv.owner_id else None
    base = dict(
        owner_id=inv.owner_id, owner_name=owner.name if owner else None, tags=inv.tags or [],
        monitor_interval_hours=inv.monitor_interval_hours, next_run_at=inv.next_run_at,
        previous_completed_at=inv.previous_completed_at, run_count=inv.run_count or 0,
        id=inv.id, seed=inv.seed, seed_type=inv.seed_type, title=inv.title, status=inv.status, error=inv.error,
        created_at=inv.created_at, updated_at=inv.updated_at, started_at=inv.started_at,
        completed_at=inv.completed_at, stats=await investigation_stats(s, inv, list(runs)),
    )
    if with_runs:
        return InvestigationDetail(**base, runs=[run_out(r) for r in latest_runs(list(runs))])
    return InvestigationOut(**base)


@dataclass
class EntityContext:
    entities: dict[str, Entity]
    matches: dict[str, EntityMatch]
    avatars: dict[str, str]
    decisions: dict[str, AnalystDecision]
    new_since: datetime | None

    def out(self, e: Entity) -> EntityOut:
        return entity_out(e, self.matches.get(e.id), self.avatars.get(e.id), self.decisions.get(e.id), self.new_since)


async def _entity_context(s: AsyncSession, investigation_id: str) -> EntityContext:
    inv = await s.get(Investigation, investigation_id)
    entities = {e.id: e for e in (await s.scalars(select(Entity).where(Entity.investigation_id == investigation_id))).all()}
    matches = {m.entity_id: m for m in (await s.scalars(
        select(EntityMatch).where(EntityMatch.investigation_id == investigation_id))).all()}
    decisions = {d.entity_id: d for d in (await s.scalars(
        select(AnalystDecision).where(AnalystDecision.investigation_id == investigation_id))).all()}
    avatars: dict[str, str] = {}
    for obs_id, entity_id in (await s.execute(
        select(Observation.id, Observation.entity_id).where(
            Observation.investigation_id == investigation_id, Observation.attribute == "avatar")
        .order_by(Observation.observed_at.desc())
    )).all():
        avatars.setdefault(entity_id, obs_id)
    return EntityContext(entities, matches, avatars, decisions, inv.previous_completed_at if inv else None)


def _entity_weight(e: Entity) -> float:
    if e.is_seed or (e.data or {}).get("subject"):
        return 1.0
    return e.confidence


async def build_profile(s: AsyncSession, inv: Investigation) -> ProfileView:
    ctx = await _entity_context(s, inv.id)
    entities, matches = ctx.entities, ctx.matches
    subject = next((e for e in entities.values() if (e.data or {}).get("subject")), None)
    seed_entity = next((e for e in entities.values() if e.is_seed), None)
    subject = subject or seed_entity
    if subject is None:
        raise LookupError("Investigation has no subject yet.")

    contributing = {
        eid: _entity_weight(e) for eid, e in entities.items()
        if e.kind not in NON_IDENTITY_KINDS and _entity_weight(e) >= IDENTITY_THRESHOLD
    }
    rows = (await s.execute(
        select(Observation, Source).join(Source, Source.id == Observation.source_id)
        .where(Observation.investigation_id == inv.id, Observation.entity_id.in_(list(contributing)))
    )).all()

    groups: dict[tuple[str, str], list[tuple[Observation, Source]]] = defaultdict(list)
    image_seen: dict[str, ImageOut] = {}
    for obs, src in rows:
        weight = contributing[obs.entity_id]
        if obs.attribute in IMAGE_ATTRIBUTES:
            conf = round(obs.confidence * weight, 4)
            prev = image_seen.get(obs.normalized_value)
            if prev is None or conf > prev.confidence:
                image_seen[obs.normalized_value] = ImageOut(
                    observation_id=obs.id, original_url=obs.value, confidence=conf, level=level(conf),
                    first_observed=obs.observed_at, last_observed=obs.observed_at, source=source_out(src),
                    entity=ref_out(entities[obs.entity_id]),
                )
            continue
        if obs.attribute in HIDDEN_IDENTITY_ATTRIBUTES:
            continue
        groups[(obs.attribute, obs.normalized_value)].append((obs, src))
    images = sorted(image_seen.values(), key=lambda i: -i.confidence)

    attributes: list[IdentityAttribute] = []
    for (attr, norm), items in groups.items():
        per_connector: dict[str, float] = {}
        evidence = []
        for obs, src in items:
            weight = contributing[obs.entity_id]
            contribution = obs.confidence * weight * RELIABILITY_WEIGHT[Reliability(src.reliability)]
            per_connector[src.connector] = max(per_connector.get(src.connector, 0.0), contribution)
            evidence.append(EvidenceItem(
                observation_id=obs.id, value=obs.value, confidence=obs.confidence, weight=round(weight, 4),
                observed_at=obs.observed_at, source=source_out(src), entity=ref_out(entities[obs.entity_id]),
            ))
        # Agreement raises confidence, but an inferred attribute is never presented as certain.
        conf = round(min(MAX_INFERRED, noisy_or(per_connector.values())), 4)
        values = [o.value for o, _ in items]
        attributes.append(IdentityAttribute(
            attribute=attr, value=max(set(values), key=values.count), normalized_value=norm, confidence=conf,
            level=level(conf), first_observed=min(o.observed_at for o, _ in items),
            last_observed=max(o.observed_at for o, _ in items), source_count=len(per_connector),
            evidence=sorted(evidence, key=lambda e: -e.confidence * e.weight),
        ))
    order = {a: i for i, a in enumerate(ATTRIBUTE_ORDER)}
    attributes.sort(key=lambda a: (order.get(a.attribute, len(order)), -a.confidence))

    profiles = sorted(
        (e for e in entities.values() if e.kind == EntityKind.PROFILE.value),
        key=lambda e: -(matches[e.id].score if e.id in matches else 0),
    )
    profile_outs = [ctx.out(e) for e in profiles]

    runs = latest_runs(list((await s.scalars(
        select(ConnectorRun).where(ConnectorRun.investigation_id == inv.id, ConnectorRun.phase == 1))).all()))
    presence = []
    for r in runs:
        c = CONNECTORS.get(r.connector)
        if not c or c.category.value not in PRESENCE_CATEGORIES:
            continue
        best = next((p for p in profile_outs if p.data.get("platform") == r.connector), None)
        presence.append(PresenceOut(
            connector=r.connector, label=c.label, category=c.category.value, status=r.status, message=r.message,
            manual_url=r.manual_url, target=r.target, profile=best,
        ))

    matched_scores = [m.score for m in matches.values() if m.score >= IDENTITY_THRESHOLD]
    overall = await _overall_confidence(s, inv, matched_scores)
    return ProfileView(
        subject=entity_out(subject), seed_entity_id=seed_entity.id if seed_entity else None,
        confidence=overall, level=level(overall) if overall is not None else None, images=images,
        attributes=attributes, presence=presence, profiles=profile_outs,
    )


async def list_entities(s: AsyncSession, investigation_id: str, kind: str | None) -> list[EntityOut]:
    ctx = await _entity_context(s, investigation_id)
    out = [ctx.out(e) for e in ctx.entities.values() if not kind or e.kind == kind]
    return sorted(out, key=lambda e: (-(e.match.score if e.match else e.confidence), e.label))


async def list_mentions(
    s: AsyncSession, investigation_id: str, category: str | None, sort: str, limit: int, offset: int
) -> MentionPage:
    """A mention authored by a profile is only as relevant to the subject as that profile's match,
    so the reported confidence is mention confidence x entity confidence."""
    effective = Mention.confidence * func.coalesce(Entity.confidence, 1.0)
    base = (select(Mention, Source, Entity, effective.label("effective"))
            .join(Source, Source.id == Mention.source_id)
            .outerjoin(Entity, Entity.id == Mention.entity_id)
            .where(Mention.investigation_id == investigation_id))
    counts = dict((await s.execute(
        select(Mention.category, func.count()).where(Mention.investigation_id == investigation_id)
        .group_by(Mention.category))).all())
    if category:
        base = base.where(Mention.category == category)
    when = func.coalesce(Mention.published_at, Mention.observed_at)
    order = {
        "newest": [when.desc()], "oldest": [when.asc()],
        "confidence": [effective.desc(), when.desc()], "source": [Source.name.asc(), when.desc()],
    }.get(sort, [when.desc()])
    rows = (await s.execute(base.order_by(*order).limit(limit).offset(offset))).all()
    total = sum(counts.values()) if not category else counts.get(category, 0)
    return MentionPage(total=total, counts=counts, items=[
        MentionOut(
            id=m.id, url=m.url, title=m.title, snippet=m.snippet, category=m.category, association=m.association,
            published_at=m.published_at, observed_at=m.observed_at, confidence=round(conf, 4),
            level=level(conf), source=source_out(src), entity=ref_out(ent) if ent else None,
        ) for m, src, ent, conf in rows
    ])


async def timeline(s: AsyncSession, investigation_id: str, kind: str | None) -> list[TimelineEventOut]:
    q = (select(TimelineEvent, Source).join(Source, Source.id == TimelineEvent.source_id)
         .where(TimelineEvent.investigation_id == investigation_id))
    if kind:
        q = q.where(TimelineEvent.kind == kind)
    rows = (await s.execute(q.order_by(TimelineEvent.occurred_at.desc()).limit(1000))).all()
    entity_ids = {ev.entity_id for ev, _ in rows if ev.entity_id}
    ents = {e.id: e for e in (await s.scalars(select(Entity).where(Entity.id.in_(entity_ids)))).all()} if entity_ids else {}
    return [
        TimelineEventOut(id=ev.id, kind=ev.kind, title=ev.title, detail=ev.detail, occurred_at=ev.occurred_at,
                         source=source_out(src), entity=ref_out(ents[ev.entity_id]) if ev.entity_id in ents else None)
        for ev, src in rows
    ]


async def build_graph(s: AsyncSession, investigation_id: str, include_mentions: bool) -> GraphOut:
    ctx = await _entity_context(s, investigation_id)
    entities, matches, avatars = ctx.entities, ctx.matches, ctx.avatars
    ranked = sorted(entities.values(), key=lambda e: (not (e.is_seed or (e.data or {}).get("subject")), -e.confidence))
    kept = {e.id: e for e in ranked[:GRAPH_NODE_LIMIT]}
    nodes = [
        GraphNode(id=e.id, kind=e.kind, label=e.label, confidence=e.confidence, level=level(e.confidence),
                  is_seed=e.is_seed, is_subject=bool((e.data or {}).get("subject")),
                  data={**(e.data or {}), "match_label": matches[e.id].label if e.id in matches else None,
                        "cluster": matches[e.id].cluster if e.id in matches else None,
                        "avatar_observation_id": avatars.get(e.id)})
        for e in kept.values()
    ]
    rels = (await s.scalars(select(Relationship).where(Relationship.investigation_id == investigation_id))).all()
    edges = [
        GraphEdge(id=r.id, source=r.src_entity_id, target=r.dst_entity_id, type=r.type, confidence=r.confidence,
                  inferred=r.source_id is None)
        for r in rels if r.src_entity_id in kept and r.dst_entity_id in kept
    ]
    if include_mentions:
        mentions = (await s.scalars(select(Mention).where(
            Mention.investigation_id == investigation_id, Mention.entity_id.is_not(None))
            .order_by(Mention.confidence.desc()).limit(60))).all()
        for m in mentions:
            if m.entity_id not in kept:
                continue
            nodes.append(GraphNode(id=f"mention:{m.id}", kind="mention", label=m.title[:80], confidence=m.confidence,
                                   level=level(m.confidence), is_seed=False, is_subject=False,
                                   data={"url": m.url, "mention_id": m.id}))
            authored = m.association.startswith("Authored")
            edges.append(GraphEdge(
                id=f"edge:{m.id}", source=m.entity_id if authored else f"mention:{m.id}",
                target=f"mention:{m.id}" if authored else m.entity_id,
                type="AUTHORED" if authored else "MENTIONS", confidence=m.confidence, inferred=False,
            ))
    return GraphOut(nodes=nodes, edges=edges, truncated=len(entities) > len(kept))


async def entity_evidence(s: AsyncSession, entity: Entity) -> EntityEvidence:
    match = await s.scalar(select(EntityMatch).where(EntityMatch.entity_id == entity.id))
    decision = await s.scalar(select(AnalystDecision).where(AnalystDecision.entity_id == entity.id))
    avatar = await s.scalar(select(Observation.id).where(Observation.entity_id == entity.id,
                                                         Observation.attribute == "avatar").limit(1))
    obs_rows = (await s.execute(
        select(Observation, Source).join(Source, Source.id == Observation.source_id)
        .where(Observation.entity_id == entity.id).order_by(Observation.attribute, Observation.observed_at.desc())
    )).all()
    rels = (await s.scalars(select(Relationship).where(
        (Relationship.src_entity_id == entity.id) | (Relationship.dst_entity_id == entity.id)))).all()
    other_ids = {r.dst_entity_id if r.src_entity_id == entity.id else r.src_entity_id for r in rels}
    others = {e.id: e for e in (await s.scalars(select(Entity).where(Entity.id.in_(other_ids)))).all()} if other_ids else {}
    src_ids = {r.source_id for r in rels if r.source_id}
    sources = {x.id: x for x in (await s.scalars(select(Source).where(Source.id.in_(src_ids)))).all()} if src_ids else {}
    relationships = []
    for r in rels:
        outgoing = r.src_entity_id == entity.id
        other = others.get(r.dst_entity_id if outgoing else r.src_entity_id)
        if other is None:
            continue
        relationships.append(RelationshipOut(
            id=r.id, type=r.type, direction="out" if outgoing else "in", other=ref_out(other),
            confidence=r.confidence, inferred=r.source_id is None, data=r.data or {},
            source=source_out(sources[r.source_id]) if r.source_id in sources else None,
        ))
    relationships.sort(key=lambda r: -r.confidence)
    return EntityEvidence(
        entity=entity_out(entity, match, avatar, decision),
        observations=[ObservationOut(id=o.id, attribute=o.attribute, value=o.value, confidence=o.confidence,
                                     observed_at=o.observed_at, source=source_out(src)) for o, src in obs_rows],
        relationships=relationships,
        mentions=await _count(s, Mention, Mention.entity_id == entity.id),
    )


async def list_sources(s: AsyncSession, investigation_id: str, category: str | None) -> list[SourceOut]:
    q = select(Source).where(Source.investigation_id == investigation_id)
    if category:
        q = q.where(Source.category == category)
    return [source_out(x) for x in (await s.scalars(q.order_by(Source.collected_at.desc()))).all()]
