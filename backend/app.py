"""
AgentX — FastAPI Application
Main application factory with middleware, CORS, routers, and startup events.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from api.routes.misc import (
    afe_router,
    feedback_router,
    health_router,
    ws_router,
)
from api.routes.runs import router as runs_router
from config.settings import settings
from core.logging import configure_logging, get_logger
from db.database import engine
from db.models import Base

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    configure_logging()
    logger.info("agentx_startup", env=settings.app_env)

    # Create tables if they don't exist (dev/test convenience)
    # In production, use Alembic migrations instead
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("dev_tables_created")

    yield

    # Graceful shutdown
    await engine.dispose()
    logger.info("agentx_shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="AgentX — Autonomous Code Review API",
        description=(
            "LangGraph-orchestrated 9-agent pipeline for bug detection "
            "and automated PR generation in research codebases."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_timing_middleware(request: Request, call_next):
        start = time.monotonic()
        response: Response = await call_next(request)
        duration = round((time.monotonic() - start) * 1000)
        response.headers["X-Process-Time-Ms"] = str(duration)
        logger.debug(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration,
        )
        return response

    # ── Exception Handlers ────────────────────────────────────────────────────

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    # ── Routers ───────────────────────────────────────────────────────────────

    app.include_router(runs_router)
    app.include_router(ws_router)
    app.include_router(feedback_router)
    app.include_router(health_router)
    app.include_router(afe_router)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": "AgentX",
            "description": "Autonomous Code Review Pipeline",
            "version": "1.0.0",
            "docs": "/docs",
            "team": "TriggeredAGIs",
            "event": "Agentic AI Hackathon 2026 | ASTRA Lab, IIT Madras",
        }

    return app


# Create the app instance
app = create_app()
