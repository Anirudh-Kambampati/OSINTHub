import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.api.routes import router
from app.config import get_settings
from app.connectors.registry import CONNECTORS
from app.core.net import HostLimiter
from app.services.orchestrator import JobRunner, Orchestrator, recover_interrupted

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Redirects are followed manually by SourceHttp so each hop is SSRF-validated.
    async with httpx.AsyncClient(follow_redirects=False, http2=False) as client:
        app.state.http = client
        app.state.limiter = HostLimiter()
        orchestrator = Orchestrator(db.session_factory(), client, settings, CONNECTORS, app.state.limiter)
        app.state.runner = JobRunner(orchestrator, settings.max_concurrent_investigations)
        await recover_interrupted(db.session_factory())
        yield
        await app.state.runner.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OSINT Intelligence Console API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)

    @app.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
