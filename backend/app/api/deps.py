import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Entity, Investigation, Observation, User
from app.services.auth import SESSION_COOKIE, user_for_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-osint-csrf"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def csrf_protect(request: Request) -> None:
    """State-changing requests must carry a custom header. Browsers can't add one cross-site
    without a CORS preflight (which our CORS policy rejects), so this blocks CSRF."""
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing CSRF header.")


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    user = await user_for_token(session, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required.")
    return user


def can_access(user: User, inv: Investigation) -> bool:
    return user.role == "admin" or inv.owner_id == user.id


def scope_investigations(query, user: User):
    return query if user.role == "admin" else query.where(Investigation.owner_id == user.id)


async def get_investigation(
    investigation_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Investigation:
    inv = await session.get(Investigation, investigation_id)
    # Same 404 for "missing" and "not yours", so ids can't be probed.
    if inv is None or not can_access(user, inv):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return inv


async def get_entity(
    entity_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Entity:
    entity = await session.get(Entity, entity_id)
    inv = await session.get(Investigation, entity.investigation_id) if entity else None
    if entity is None or inv is None or not can_access(user, inv):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found.")
    return entity


async def get_observation(
    observation_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Observation:
    obs = await session.get(Observation, observation_id)
    inv = await session.get(Investigation, obs.investigation_id) if obs else None
    if obs is None or inv is None or not can_access(user, inv):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return obs


class SlidingWindowLimiter:
    """Per-process limiter (used for login attempts). Investigation creation is limited in the DB."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            retry = int(window - (now - hits[0])) + 1
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts; try again shortly.",
                                headers={"Retry-After": str(retry)})
        hits.append(now)


login_limiter = SlidingWindowLimiter()


async def rate_limit_login(request: Request, settings: Settings = Depends(get_settings)) -> None:
    login_limiter.check(f"login:{client_ip(request)}", settings.login_rate_limit_per_minute)


async def rate_limit_investigations(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    """Counted in the database so the limit holds across API replicas."""
    since = datetime.now(UTC) - timedelta(minutes=1)
    recent = await session.scalar(select(func.count()).select_from(Investigation).where(
        Investigation.owner_id == user.id, Investigation.updated_at >= since,
        Investigation.status.in_(["pending", "running"])))
    if (recent or 0) >= settings.create_rate_limit_per_minute:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many investigations started; slow down.",
                            headers={"Retry-After": "60"})
