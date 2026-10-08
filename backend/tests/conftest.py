import os
import tempfile
from typing import Any

import httpx
import pytest

from app import db
from app.api.deps import login_limiter
from app.config import get_settings
from app.connectors._profile import PublicProfile, emit_profile
from app.connectors.base import Connector, ConnectorContext, ConnectorError, ConnectorResult, Findings
from app.connectors.registry import CONNECTORS
from app.core.enums import Reliability, RunStatus, SeedType, SourceCategory
from app.core.net import HostLimiter
from app.main import create_app
from app.services.orchestrator import Orchestrator
from app.services.worker import Worker


class FakeProfileConnector(Connector):
    """Deterministic connector for pipeline/API tests. No network."""

    category = SourceCategory.SOCIAL
    reliability = Reliability.HIGH
    supports = frozenset({SeedType.USERNAME})

    def __init__(self, name: str, profile: PublicProfile | None = None, *, error: Exception | None = None):
        self.name = name
        self.label = name.title()
        self._profile = profile
        self._error = error

    async def fetch(self, target: str, seed_type: SeedType, ctx: ConnectorContext) -> Any:
        if self._error:
            raise self._error
        return self._profile

    def normalize(self, raw: Any, target: str, seed_type: SeedType) -> ConnectorResult:
        f = Findings(self.name)
        if raw is None:
            return ConnectorResult(RunStatus.NOT_FOUND, f, "Not found.")
        emit_profile(f, raw, category=self.category, reliability=self.reliability)
        return ConnectorResult(RunStatus.FOUND, f)


def fake_connectors() -> dict[str, Connector]:
    return {
        "github": FakeProfileConnector("github", PublicProfile(
            platform="github", username="anirudh123", url="https://github.com/anirudh123", name="Anirudh K",
            email="anirudh@example.com", linked_accounts=["devto:anirudh123"],
        )),
        "devto": FakeProfileConnector("devto", PublicProfile(
            platform="devto", username="anirudh123", url="https://dev.to/anirudh123", name="Anirudh K",
            email="anirudh@example.com",
        )),
        "gitlab": FakeProfileConnector("gitlab", None),
        "broken": FakeProfileConnector("broken", error=ConnectorError("Upstream exploded")),
        "crashy": FakeProfileConnector("crashy", error=RuntimeError("bug in parser")),
    }


@pytest.fixture
async def database():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with db.engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    yield db.session_factory()
    await db.engine.dispose()
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def connectors(monkeypatch):
    """Swap the global registry for fakes (the dict object is shared by routes/views/orchestrator)."""
    original = dict(CONNECTORS)
    CONNECTORS.clear()
    CONNECTORS.update(fake_connectors())
    yield CONNECTORS
    CONNECTORS.clear()
    CONNECTORS.update(original)


@pytest.fixture
async def orchestrator(database, connectors):
    async with httpx.AsyncClient() as client:
        yield Orchestrator(database, client, get_settings(), connectors)


ADMIN = {"email": "admin@example.com", "name": "Admin", "password": "correct-horse-battery-1"}


@pytest.fixture
async def anon_api(database, connectors):
    """Unauthenticated client; the worker is driven explicitly with `worker.run_until_idle()`."""
    app = create_app()
    async with httpx.AsyncClient() as outbound:
        app.state.http = outbound
        app.state.limiter = HostLimiter()
        app.state.worker = Worker(Orchestrator(database, outbound, get_settings(), connectors), database,
                                  get_settings(), worker_id="test-worker")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     headers={"X-OSINT-CSRF": "1"}) as client:
            client.app = app  # type: ignore[attr-defined]
            yield client


@pytest.fixture
async def api(anon_api):
    """Client signed in as the bootstrap admin."""
    resp = await anon_api.post("/api/auth/register", json=ADMIN)
    assert resp.status_code == 201, resp.text
    return anon_api


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    login_limiter._hits.clear()
