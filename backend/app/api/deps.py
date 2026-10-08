import hmac
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Investigation

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    """If OSINT_API_TOKEN is configured, every API call must present it (constant-time compare)."""
    if settings.api_token is None:
        return
    expected = settings.api_token.get_secret_value().encode()
    if creds is None or not hmac.compare_digest(creds.credentials.encode(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API token.",
                            headers={"WWW-Authenticate": "Bearer"})


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            retry = int(window - (now - hits[0])) + 1
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many investigations started; slow down.",
                                headers={"Retry-After": str(retry)})
        hits.append(now)


limiter = SlidingWindowLimiter()


async def rate_limit_investigations(request: Request, settings: Settings = Depends(get_settings)) -> None:
    client = request.client.host if request.client else "unknown"
    limiter.check(f"create:{client}", settings.create_rate_limit_per_minute)


async def get_investigation(investigation_id: str, session: AsyncSession = Depends(get_session)) -> Investigation:
    inv = await session.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return inv
