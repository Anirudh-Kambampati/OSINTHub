import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    client_ip, csrf_protect, current_user, get_entity, get_investigation, get_observation, rate_limit_investigations,
    scope_investigations,
)
from app.config import Settings, get_settings
from app.connectors.registry import CONNECTORS
from app.core.classify import ClassificationError, classify, classify_as
from app.core.enums import EntityKind, InvestigationStatus
from app.core.net import ResponseTooLarge, SourceHttp, UnsafeURLError
from app.db import get_session
from app.models import (
    AccessLog, AnalystDecision, Entity, Investigation, InvestigationNote, Observation, User,
)
from app.schemas import (
    AccessLogOut, ClassifyIn, ClassifyOut, ConnectorInfo, DecisionIn, EntityEvidence, EntityOut, GraphOut,
    InvestigationCreate, InvestigationDetail, InvestigationOut, InvestigationUpdate, MentionPage, NoteIn, NoteOut,
    ProfileView, SourceOut, TimelineEventOut,
)
from app.services import export, views
from app.services.auth import audit
from app.services.orchestrator import plan_runs
from app.services.resolution import run_resolution
from app.services.worker import enqueue_rerun

router = APIRouter(prefix="/api", dependencies=[Depends(csrf_protect), Depends(current_user)])

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}
ACTIVE = [InvestigationStatus.PENDING.value, InvestigationStatus.RUNNING.value]
TAG_RE = re.compile(r"^[\w .:/-]{1,32}$")


def _wake_worker(request: Request) -> None:
    worker = getattr(request.app.state, "worker", None)
    if worker is not None:
        worker.wake()


def _filename(inv: Investigation, ext: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", inv.seed)[:40].strip("-") or "investigation"
    return f"osint-{slug}-{datetime.now(UTC):%Y%m%d}.{ext}"


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


# --- investigations -----------------------------------------------------------------------

@router.get("/investigations", response_model=list[InvestigationOut])
async def list_investigations(
    limit: int = Query(100, ge=1, le=500), q: str | None = Query(None, max_length=128),
    tag: str | None = Query(None, max_length=32),
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
) -> list[InvestigationOut]:
    query = scope_investigations(select(Investigation), user).order_by(Investigation.created_at.desc())
    if q:
        like = f"%{q.lower()}%"
        query = query.where(Investigation.seed_normalized.ilike(like) | Investigation.title.ilike(like))
    invs = (await session.scalars(query.limit(limit))).all()
    if tag:
        invs = [i for i in invs if tag in (i.tags or [])]
    return [await views.investigation_out(session, inv, with_runs=False) for inv in invs]


@router.post("/investigations", response_model=InvestigationDetail, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit_investigations)])
async def create_investigation(
    body: InvestigationCreate, request: Request, user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> InvestigationDetail:
    try:
        c = classify_as(body.seed, body.seed_type) if body.seed_type else classify(body.seed)
    except ClassificationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    inv = Investigation(seed=body.seed.strip(), seed_normalized=c.normalized, seed_type=c.type.value,
                        title=c.normalized, status=InvestigationStatus.PENDING.value, owner_id=user.id, tags=[])
    session.add(inv)
    await session.flush()
    session.add_all(plan_runs(inv.id, c, CONNECTORS))
    audit(session, user, "investigation.create", f"{inv.id} {c.type.value}:{c.normalized}", client_ip(request))
    await session.commit()
    _wake_worker(request)
    return await views.investigation_out(session, inv, with_runs=True)


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetail)
async def get_investigation_detail(
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)
) -> InvestigationDetail:
    return await views.investigation_out(session, inv, with_runs=True)


@router.patch("/investigations/{investigation_id}", response_model=InvestigationDetail)
async def update_investigation(
    body: InvestigationUpdate, inv: Investigation = Depends(get_investigation),
    session: AsyncSession = Depends(get_session),
) -> InvestigationDetail:
    if body.title is not None:
        inv.title = body.title.strip()
    if body.tags is not None:
        tags = sorted({t.strip() for t in body.tags if t.strip()})
        if any(not TAG_RE.match(t) for t in tags):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tags are short words (letters, digits, - . : /).")
        inv.tags = tags
    if "monitor_interval_hours" in body.model_fields_set:
        inv.monitor_interval_hours = body.monitor_interval_hours
        inv.next_run_at = (
            (inv.completed_at or datetime.now(UTC)) + timedelta(hours=body.monitor_interval_hours)
            if body.monitor_interval_hours and inv.status not in ACTIVE else None
        )
    await session.commit()
    return await views.investigation_out(session, inv, with_runs=True)


@router.delete("/investigations/{investigation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investigation(
    request: Request, inv: Investigation = Depends(get_investigation), user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if inv.status in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Investigation is still running.")
    audit(session, user, "investigation.delete", f"{inv.id} {inv.seed}", client_ip(request))
    await session.execute(delete(AccessLog).where(AccessLog.investigation_id == inv.id))
    await session.delete(inv)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/investigations/{investigation_id}/search", response_model=InvestigationDetail,
             dependencies=[Depends(rate_limit_investigations)])
async def rerun_investigation(
    request: Request, inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session),
) -> InvestigationDetail:
    """Re-query all sources. New observations are appended, so first/last-observed dates accumulate."""
    if inv.status in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Investigation is already running.")
    await enqueue_rerun(session, inv)
    await session.commit()
    _wake_worker(request)
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
    limit: int = Query(50, ge=1, le=500),
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


@router.get("/investigations/{investigation_id}/access-log", response_model=list[AccessLogOut])
async def get_access_log(inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)):
    return (await session.scalars(select(AccessLog).where(AccessLog.investigation_id == inv.id)
                                  .order_by(AccessLog.at.desc()).limit(1000))).all()


# --- notes ----------------------------------------------------------------------------------

async def _note_out(session: AsyncSession, n: InvestigationNote) -> NoteOut:
    author = await session.get(User, n.author_id) if n.author_id else None
    return NoteOut(id=n.id, body=n.body, author_id=n.author_id, author_name=author.name if author else None,
                   created_at=n.created_at)


@router.get("/investigations/{investigation_id}/notes", response_model=list[NoteOut])
async def list_notes(inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)):
    notes = (await session.scalars(select(InvestigationNote).where(InvestigationNote.investigation_id == inv.id)
                                   .order_by(InvestigationNote.created_at.desc()))).all()
    return [await _note_out(session, n) for n in notes]


@router.post("/investigations/{investigation_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def add_note(body: NoteIn, inv: Investigation = Depends(get_investigation), user: User = Depends(current_user),
                   session: AsyncSession = Depends(get_session)):
    note = InvestigationNote(investigation_id=inv.id, author_id=user.id, body=body.body.strip())
    session.add(note)
    await session.commit()
    return await _note_out(session, note)


@router.delete("/investigations/{investigation_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: str, inv: Investigation = Depends(get_investigation), user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    note = await session.get(InvestigationNote, note_id)
    if note is None or note.investigation_id != inv.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found.")
    if note.author_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own notes.")
    await session.delete(note)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- exports --------------------------------------------------------------------------------

@router.get("/investigations/{investigation_id}/export.json")
async def export_json(inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)):
    return JSONResponse(await export.export_json(session, inv),
                        headers={"Content-Disposition": f'attachment; filename="{_filename(inv, "json")}"'})


@router.get("/investigations/{investigation_id}/export.csv")
async def export_csv(
    dataset: Literal["attributes", "profiles", "mentions", "observations", "timeline", "sources"] = "observations",
    inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session),
):
    body = await export.export_csv(session, inv, dataset)
    return PlainTextResponse("﻿" + body, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{_filename(inv, dataset + ".csv")}"'})


@router.get("/investigations/{investigation_id}/report.html")
async def export_report(inv: Investigation = Depends(get_investigation), session: AsyncSession = Depends(get_session)):
    html = await export.export_report_html(session, inv)
    return HTMLResponse(html, headers={
        # The report is static: no scripts, no external loads.
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
    })


# --- entities, decisions, images ------------------------------------------------------------

@router.get("/entities/{entity_id}", response_model=EntityOut)
async def get_entity_detail(entity: Entity = Depends(get_entity), session: AsyncSession = Depends(get_session)):
    return (await views.entity_evidence(session, entity)).entity


@router.get("/entities/{entity_id}/evidence", response_model=EntityEvidence)
async def get_entity_evidence(entity: Entity = Depends(get_entity), session: AsyncSession = Depends(get_session)):
    return await views.entity_evidence(session, entity)


async def _reresolve(session: AsyncSession, entity: Entity) -> EntityEvidence:
    inv = await session.get(Investigation, entity.investigation_id)
    await run_resolution(session, inv)
    await session.commit()
    return await views.entity_evidence(session, entity)


@router.put("/entities/{entity_id}/decision", response_model=EntityEvidence)
async def set_decision(body: DecisionIn, request: Request, entity: Entity = Depends(get_entity),
                       user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """Analyst verdict on a profile. Re-runs resolution so identity, clusters and scores update."""
    if entity.kind != EntityKind.PROFILE.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Decisions apply to discovered profiles.")
    row = await session.scalar(select(AnalystDecision).where(AnalystDecision.entity_id == entity.id))
    if row is None:
        row = AnalystDecision(investigation_id=entity.investigation_id, entity_id=entity.id)
        session.add(row)
    row.decision, row.note, row.user_id, row.created_at = body.decision, body.note, user.id, datetime.now(UTC)
    audit(session, user, f"decision.{body.decision}", f"{entity.investigation_id} {entity.key}", client_ip(request))
    await session.flush()
    return await _reresolve(session, entity)


@router.delete("/entities/{entity_id}/decision", response_model=EntityEvidence)
async def clear_decision(request: Request, entity: Entity = Depends(get_entity), user: User = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    await session.execute(delete(AnalystDecision).where(AnalystDecision.entity_id == entity.id))
    audit(session, user, "decision.cleared", f"{entity.investigation_id} {entity.key}", client_ip(request))
    await session.flush()
    return await _reresolve(session, entity)


@router.get("/observations/{observation_id}/image")
async def proxy_image(request: Request, obs: Observation = Depends(get_observation)):
    """Serve a profile image through the backend so investigators' browsers never contact the
    platform directly. Only URLs that were actually observed can be fetched (no open proxy)."""
    if obs.attribute not in ("avatar", "image"):
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
