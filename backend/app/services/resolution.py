"""Applies the pure resolver to stored observations and persists the outcome."""

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import EntityRef
from app.core.classify import Classification
from app.core.confidence import IDENTITY_THRESHOLD
from app.core.enums import EntityKind, RelType, SeedType
from app.core.normalize import normalize_url, normalize_username
from app.models import AnalystDecision, Entity, EntityMatch, Investigation, Observation, Relationship
from app.services.resolver import Candidate, resolve
from app.services.store import upsert_entity, upsert_relationship

SUBJECT_NAME_THRESHOLD = 0.60
RESOLVER_ATTRIBUTES = ("username", "name", "email", "website", "linked_account", "organization", "location")


def seed_entity_ref(seed: Classification) -> EntityRef:
    match seed.type:
        case SeedType.USERNAME:
            return EntityRef(EntityKind.USERNAME, normalize_username(seed.normalized))
        case SeedType.EMAIL:
            return EntityRef(EntityKind.EMAIL, seed.normalized)
        case SeedType.DOMAIN:
            return EntityRef(EntityKind.DOMAIN, seed.normalized)
        case SeedType.URL:
            return EntityRef(EntityKind.WEBSITE, normalize_url(seed.normalized))
        case _:
            return EntityRef(EntityKind.PERSON, "subject")


def subject_is_person(seed: Classification) -> bool:
    return seed.type in (SeedType.USERNAME, SeedType.EMAIL, SeedType.PERSON)


async def ensure_subject(session: AsyncSession, inv: Investigation) -> tuple[str, str]:
    """Create the seed entity and the subject (the 'who/what' being investigated). Returns (subject_id, seed_id)."""
    seed = Classification(SeedType(inv.seed_type), inv.seed_normalized)
    ref = seed_entity_ref(seed)
    seed_id = await upsert_entity(session, inv.id, ref, inv.seed_normalized, is_seed=True)
    if not subject_is_person(seed):
        return seed_id, seed_id
    subject_id = await upsert_entity(session, inv.id, EntityRef(EntityKind.PERSON, "subject"), inv.title,
                                     {"subject": True})
    if subject_id != seed_id:
        await upsert_relationship(session, inv.id, subject_id, seed_id, RelType.USES.value, 1.0, None,
                                  {"inferred": True, "reason": "Investigation seed"})
    return subject_id, seed_id


async def run_resolution(session: AsyncSession, inv: Investigation) -> None:
    seed = Classification(SeedType(inv.seed_type), inv.seed_normalized)
    subject_id, seed_id = await ensure_subject(session, inv)

    entities = (await session.scalars(
        select(Entity).where(Entity.investigation_id == inv.id,
                             Entity.kind.in_([EntityKind.PROFILE.value, EntityKind.WEBSITE.value]))
    )).all()
    by_id = {e.id: e for e in entities}
    observations = (await session.scalars(
        select(Observation).where(Observation.investigation_id == inv.id,
                                  Observation.entity_id.in_(list(by_id)),
                                  Observation.attribute.in_(RESOLVER_ATTRIBUTES))
    )).all()

    candidates: dict[str, Candidate] = {}
    for e in entities:
        is_profile = e.kind == EntityKind.PROFILE.value
        candidates[e.id] = Candidate(
            entity_id=e.id, identity=e.key if is_profile else f"site:{e.key}",
            label=(e.data or {}).get("platform_label", "") + " " + e.label if is_profile else e.label,
            is_profile=is_profile,
        )
    claim_sources: dict[tuple[str, str], tuple[str, float]] = {}
    for o in observations:
        c = candidates[o.entity_id]
        match o.attribute:
            case "username":
                c.username = c.username or o.value
            case "name":
                c.names.add(o.normalized_value)
            case "email":
                c.emails.add(o.normalized_value)
            case "website":
                c.websites.add(o.normalized_value)
            case "linked_account":
                c.linked_accounts[o.normalized_value] = max(c.linked_accounts.get(o.normalized_value, 0), o.confidence)
                claim_sources[(o.entity_id, o.normalized_value)] = (o.source_id, o.confidence)
            case "organization":
                c.organizations.add(o.normalized_value)
            case "location":
                c.locations.add(o.normalized_value)
    for c in candidates.values():
        c.label = c.label.strip()

    decisions = dict((await session.execute(
        select(AnalystDecision.entity_id, AnalystDecision.decision).where(AnalystDecision.investigation_id == inv.id)
    )).all())
    results = resolve(list(candidates.values()), seed.type, seed.normalized, decisions)

    await session.execute(delete(EntityMatch).where(EntityMatch.investigation_id == inv.id))
    for entity_id, result in results.items():
        session.add(EntityMatch(investigation_id=inv.id, entity_id=entity_id, score=result.score, label=result.label,
                                factors=[f.as_dict() for f in result.factors], cluster=result.cluster))
        by_id[entity_id].confidence = result.score

    # Cross-links observed on profiles/websites become LINKS_TO edges when the target was found.
    identity_index = {c.identity: c.entity_id for c in candidates.values()}
    for (entity_id, claim), (source_id, conf) in claim_sources.items():
        if (target := identity_index.get(claim)) and target != entity_id:
            await upsert_relationship(session, inv.id, entity_id, target, RelType.LINKS_TO.value, conf, source_id)

    # Subject associations are inferences: they carry factors, not a source.
    await session.execute(delete(Relationship).where(
        Relationship.investigation_id == inv.id, Relationship.src_entity_id == subject_id,
        Relationship.type == RelType.ASSOCIATED_WITH.value, Relationship.source_id.is_(None),
    ))
    matched = {eid: r for eid, r in results.items() if r.score >= IDENTITY_THRESHOLD}
    for entity_id, result in matched.items():
        await upsert_relationship(session, inv.id, subject_id, entity_id, RelType.ASSOCIATED_WITH.value,
                                  result.score, None, {"inferred": True, "label": result.label})

    await _propagate_confidence(session, inv.id, subject_id, seed_id, matched)
    await _label_subject(session, inv, subject_id, matched, subject_is_person(seed))
    await session.flush()


async def _propagate_confidence(session, investigation_id, subject_id, seed_id, matched) -> None:
    """Identifier entities inherit confidence from the matched profiles that reference them."""
    rels = (await session.scalars(select(Relationship).where(Relationship.investigation_id == investigation_id))).all()
    entities = (await session.scalars(select(Entity).where(Entity.investigation_id == investigation_id))).all()
    weight = {eid: r.score for eid, r in matched.items()}
    weight[subject_id] = weight[seed_id] = 1.0
    best: dict[str, float] = defaultdict(float)
    for _ in range(2):  # two hops: profile -> website -> domain
        for r in rels:
            # PART_OF also flows backwards: a website/subdomain of a relevant domain is relevant.
            # Other edges never do (e.g. every unmatched profile USES the seed username).
            directions = [(r.src_entity_id, r.dst_entity_id)]
            if r.type == RelType.PART_OF.value:
                directions.append((r.dst_entity_id, r.src_entity_id))
            for src, dst in directions:
                if src in weight and dst not in matched:
                    value = weight[src] * r.confidence
                    if value > best[dst]:
                        best[dst] = value
        for eid, value in best.items():
            weight.setdefault(eid, value)
    for e in entities:
        if e.kind == EntityKind.PROFILE.value:
            continue
        e.confidence = 1.0 if e.id in (subject_id, seed_id) else round(best.get(e.id, 0.0), 4)


async def _label_subject(session, inv, subject_id, matched, is_person) -> None:
    """Name the subject only from profiles that are at least 'likely' the same entity;
    a name seen on a merely 'possible' match must not become the headline identity."""
    if not is_person:
        return
    subject = await session.get(Entity, subject_id)
    strong = {eid: r for eid, r in matched.items() if r.score >= SUBJECT_NAME_THRESHOLD}
    names = (await session.scalars(select(Observation).where(
        Observation.entity_id.in_(list(strong)), Observation.attribute == "name"))).all()
    scored: dict[str, float] = defaultdict(float)
    display: dict[str, str] = {}
    for o in names:
        scored[o.normalized_value] += o.confidence * strong[o.entity_id].score
        display.setdefault(o.normalized_value, o.value)
    subject.label = display[max(scored, key=scored.get)] if scored else inv.seed_normalized
    inv.title = subject.label
