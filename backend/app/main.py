import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import db
from app.api.auth_routes import router as auth_router
from app.api.routes import router
from app.config import get_settings
from app.connectors.registry import CONNECTORS
from app.core.net import HostLimiter
from app.logging_setup import configure_logging
from app.services.orchestrator import Orchestrator
from app.services.worker import Worker

log = logging.getLogger("osint.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_json)
    # Redirects are followed manually by SourceHttp so each hop is SSRF-validated.
    async with httpx.AsyncClient(follow_redirects=False) as client:
        app.state.http = client
        app.state.limiter = HostLimiter()
        orchestrator = Orchestrator(db.session_factory(), client, settings, CONNECTORS, app.state.limiter)
        app.state.worker = Worker(orchestrator, db.session_factory(), settings)
        stop = asyncio.Event()
        task = asyncio.create_task(app.state.worker.run_forever(stop)) if settings.run_worker_in_api else None
        yield
        stop.set()
        if task:
            app.state.worker.wake()
            with suppress(asyncio.CancelledError):
                await task


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OSINT Intelligence Console API", version="1.0.0", lifespan=lifespan,
                  docs_url=None if settings.is_production else "/docs", redoc_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-OSINT-CSRF"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"request_id": request_id})
            response = JSONResponse({"detail": "Internal server error.", "request_id": request_id}, status_code=500)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith("/api"):
            log.info("%s %s %s", request.method, request.url.path, response.status_code, extra={
                "request_id": request_id, "method": request.method, "path": request.url.path,
                "status": response.status_code, "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

    app.include_router(auth_router)
    app.include_router(router)

    @app.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def ready():
        try:
            async with db.session_factory()() as s:
                await s.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "database unavailable"}, status_code=503)
        return {"status": "ready"}

    return app


app = create_app()
