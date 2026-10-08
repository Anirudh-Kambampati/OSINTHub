from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_investigation, rate_limit_investigations, require_auth
from app.config import Settings, get_settings
from app.connectors.registry import CONNECTORS
from app.core.classify import Classification, ClassificationError, classify, classify_as
from app.core.enums import EntityKind, InvestigationStatus, SeedType
from app.core.net import ResponseTooLarge, SourceHttp, UnsafeURLError
from app.db import get_session
from app.models import Entity, Investigation, Observation
from app.schemas import (
    ClassifyIn, ClassifyOut, ConnectorInfo, EntityEvidence, EntityOut, GraphOut, InvestigationCreate,
    InvestigationDetail, InvestigationOut, MentionPage, ProfileView, SourceOut, TimelineEventOut,
)
from app.services import views
from app.services.orchestrator import plan_runs

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}


def _runner(request: Request):
    return request.app.state.runner


@router.post("/classify", response_model=ClassifyOut)
async def classify_input(body: ClassifyIn) -> ClassifyOut:
    try:
        c = classify(body.value)
    except ClassificationError as exc:
        return ClassifyOut(valid=False, error=str(exc))
    return ClassifyOut(valid=True, type=c.type, normalized=c.normalized, alternatives=c.alternatives)


@router.get("/connectors", response_model=list[ConnectorInfo])
async def list_connectors(settings: Settings = Depends(get_settings)) -> list[ConnectorInfo]:
    return [
        ConnectorInfo(
            name=c.name, label=c.label, category=c.category.value, reliability=c.reliability.value,
            supports=sorted(c.supports), accepts_pivots=sorted(c.accepts_pivots), description=c.description,
            configured=c.is_configured(settings), requires=[f"OSINT_{r.upper()}" for r in c.requires],
        )
        for c in CONNECTORS.values()
    ]


@router.get("/investigations", response_model=list[InvestigationOut])
async def list_investigations(
    limit: int = Query(50, ge=1, le=200), session: AsyncSession = Depends(get_session)
) -> list[InvestigationOut]:
    invs = (await session.scalars(select(Investigation).order_by(Investigation.created_at.desc()).limit(limit))).all()
    return [await views.investigation_out(session, inv, with_runs=False) for inv in invs]


@router.post("/investigations", response_model=InvestigationDetail, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit_investigations)])
async def create_investigation(
    body: InvestigationCreate, request: Request, session: AsyncSession = Depends(get_session)
) -> InvestigationDetail:
    try:
        c = classify_as(body.seed, body.seed_type) if body.seed_type else classify(body.seed)
    except ClassificationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    inv = Investigation(seed=body.seed.strip(), seed_normalized=c.normalized, seed_type=c.type.value,
                        title=c.normalized, status=InvestigationStatus.PENDING.value)
    session.add(inv)
    await session.flush()
    session.add_all(plan_runs(inv.id, c, CONNECTORS))
    await session.commit()
    _runner(request).submit(inv.id)
    return await views.investigation_out(session, inv, with_runs=True)


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetail)
async def get_investigation_detail(
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)
) -> InvestigationDetail:
    return await views.investigation_out(session, inv, with_runs=True)


@router.delete("/investigations/{investigation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investigation(
    request: Request, inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)
) -> Response:
    if _runner(request).is_active(inv.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Investigation is still running.")
    await session.delete(inv)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/investigations/{investigation_id}/search", response_model=InvestigationDetail,
             dependencies=[Depends(rate_limit_investigations)])
async def rerun_investigation(
    request: Request, inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)
) -> InvestigationDetail:
    """Re-query all sources. New observations are appended, so first/last-observed dates accumulate."""
    if _runner(request).is_active(inv.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Investigation is already running.")
    session.add_all(plan_runs(inv.id, Classification(SeedType(inv.seed_type), inv.seed_normalized), CONNECTORS))
    inv.status = InvestigationStatus.PENDING.value
    inv.completed_at = None
    await session.commit()
    _runner(request).submit(inv.id)
    return await views.investigation_out(session, inv, with_runs=True)


@router.get("/investigations/{investigation_id}/profile", response_model=ProfileView)
async def get_profile(inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)):
    try:
        return await views.build_profile(session, inv)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/investigations/{investigation_id}/entities", response_model=list[EntityOut])
async def get_entities(
    kind: EntityKind | None = None,
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session),
):
    return await views.list_entities(session, inv.id, kind.value if kind else None)


@router.get("/investigations/{investigation_id}/mentions", response_model=MentionPage)
async def get_mentions(
    category: str | None = Query(None, max_length=32),
    sort: Literal["newest", "oldest", "confidence", "source"] = "newest",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session),
):
    return await views.list_mentions(session, inv.id, category, sort, limit, offset)


@router.get("/investigations/{investigation_id}/timeline", response_model=list[TimelineEventOut])
async def get_timeline(
    kind: str | None = Query(None, max_length=32),
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session),
):
    return await views.timeline(session, inv.id, kind)


@router.get("/investigations/{investigation_id}/graph", response_model=GraphOut)
async def get_graph(
    include_mentions: bool = False,
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session),
):
    return await views.build_graph(session, inv.id, include_mentions)


@router.get("/investigations/{investigation_id}/sources", response_model=list[SourceOut])
async def get_sources(
    category: str | None = Query(None, max_length=32),
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session),
):
    return await views.list_sources(session, inv.id, category)


async def _entity_or_404(entity_id: str, session: AsyncSession) -> Entity:
    entity = await session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found.")
    return entity


@router.get("/entities/{entity_id}", response_model=EntityOut)
async def get_entity(entity_id: str, session: AsyncSession = Depends(get_session)):
    return (await views.entity_evidence(session, await _entity_or_404(entity_id, session))).entity


@router.get("/entities/{entity_id}/evidence", response_model=EntityEvidence)
async def get_entity_evidence(entity_id: str, session: AsyncSession = Depends(get_session)):
    return await views.entity_evidence(session, await _entity_or_404(entity_id, session))


@router.get("/observations/{observation_id}/image")
async def proxy_image(observation_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    """Serve a profile image through the backend so investigators' browsers never contact the
    platform directly. Only URLs that were actually observed can be fetched (no open proxy)."""
    obs = await session.get(Observation, observation_id)
    if obs is None or obs.attribute not in ("avatar", "image"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found.")
    settings = get_settings()
    http = SourceHttp(request.app.state.http, settings, request.app.state.limiter, "image_proxy", [])
    try:
        resp = await http.get(obs.value, max_bytes=settings.max_image_bytes, headers={"Accept": "image/*"})
    except (UnsafeURLError, ResponseTooLarge) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Image unavailable.") from exc
    except Exception as exc:  # network errors
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Image unavailable.") from exc
    if resp.status_code != 200 or resp.content_type not in IMAGE_TYPES:  # SVG deliberately excluded
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Image unavailable.")
    return Response(resp.content, media_type=resp.content_type, headers={
        "Cache-Control": "private, max-age=86400",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    })
