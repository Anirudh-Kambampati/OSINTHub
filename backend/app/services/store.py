"""Persist connector Findings. Entities are upserted by (kind, key); observations are append-only."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import EntityRef, Findings
from app.models import Entity, Mention, Observation, Relationship, Source, TimelineEvent


async def persist_findings(
    session: AsyncSession, investigation_id: str, run_id: str | None, findings: Findings
) -> int:
    """Write findings; returns the number of observations + mentions stored."""
    source_ids: dict[int, str] = {}
    for s in findings.sources:
        row = Source(
            investigation_id=investigation_id, run_id=run_id, connector=findings.connector, name=s.name,
            category=s.category.value, kind=s.kind, url=s.url[:2048], title=s.title,
            reliability=s.reliability.value, collected_at=s.collected_at,
        )
        session.add(row)
        await session.flush()
        source_ids[s.ref] = row.id

    entity_ids: dict[EntityRef, str] = {}
    for ref, rec in findings.entities.items():
        entity_ids[ref] = await upsert_entity(session, investigation_id, ref, rec.label, rec.data)

    for o in findings.observations:
        session.add(Observation(
            investigation_id=investigation_id, entity_id=entity_ids[o.entity], source_id=source_ids[o.source],
            attribute=o.attribute, value=o.value, normalized_value=o.normalized_value, confidence=o.confidence,
            observed_at=findings.sources[o.source].collected_at,
        ))

    for r in findings.relationships:
        await upsert_relationship(
            session, investigation_id, entity_ids[r.src], entity_ids[r.dst], r.type.value, r.confidence,
            source_ids[r.source],
        )

    stored_mentions = 0
    for m in findings.mentions:
        existing = await session.scalar(
            select(Mention).where(Mention.investigation_id == investigation_id, Mention.url == m.url[:2048])
        )
        if existing:
            existing.confidence = max(existing.confidence, m.confidence)
            continue
        session.add(Mention(
            investigation_id=investigation_id, entity_id=entity_ids.get(m.entity) if m.entity else None,
            source_id=source_ids[m.source], category=m.category.value, url=m.url[:2048], title=m.title[:512],
            snippet=m.snippet, association=m.association, published_at=m.published_at,
            observed_at=findings.sources[m.source].collected_at, confidence=m.confidence,
        ))
        stored_mentions += 1

    for e in findings.events:
        entity_key = f"{e.entity.kind}:{e.entity.key}" if e.entity else ""
        dedupe = f"{e.kind}|{e.title}|{e.occurred_at.isoformat()}|{entity_key}"[:1024]
        exists = await session.scalar(
            select(TimelineEvent.id).where(
                TimelineEvent.investigation_id == investigation_id, TimelineEvent.dedupe_key == dedupe
            )
        )
        if not exists:
            session.add(TimelineEvent(
                investigation_id=investigation_id, entity_id=entity_ids.get(e.entity) if e.entity else None,
                source_id=source_ids[e.source], kind=e.kind.value, title=e.title[:512], detail=e.detail,
                occurred_at=e.occurred_at, dedupe_key=dedupe,
            ))
    await session.flush()
    return len(findings.observations) + stored_mentions


async def upsert_entity(
    session: AsyncSession, investigation_id: str, ref: EntityRef, label: str, data: dict | None = None,
    *, is_seed: bool = False,
) -> str:
    row = await session.scalar(
        select(Entity).where(Entity.investigation_id == investigation_id, Entity.kind == ref.kind.value,
                             Entity.key == ref.key[:1024])
    )
    if row is None:
        row = Entity(investigation_id=investigation_id, kind=ref.kind.value, key=ref.key[:1024],
                     label=label[:512], data=data or {}, is_seed=is_seed)
        session.add(row)
        await session.flush()
    else:
        if data:
            row.data = {**(row.data or {}), **data}
        if row.label == row.key and label != row.key:
            row.label = label[:512]
        row.is_seed = row.is_seed or is_seed
    return row.id


async def upsert_relationship(
    session: AsyncSession, investigation_id: str, src_id: str, dst_id: str, type_: str, confidence: float,
    source_id: str | None, data: dict | None = None,
) -> None:
    if src_id == dst_id:
        return
    row = await session.scalar(
        select(Relationship).where(Relationship.src_entity_id == src_id, Relationship.dst_entity_id == dst_id,
                                   Relationship.type == type_)
    )
    if row is None:
        session.add(Relationship(
            investigation_id=investigation_id, src_entity_id=src_id, dst_entity_id=dst_id, type=type_,
            confidence=confidence, source_id=source_id, data=data or {},
        ))
        await session.flush()
    else:
        row.confidence = max(row.confidence, confidence) if source_id else confidence
        if data is not None:
            row.data = data
        if row.source_id is None and source_id:
            row.source_id = source_id
