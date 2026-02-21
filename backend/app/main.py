"""
FastAPI application factory for TalentCopilot.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.infrastructure.database.connection import engine, async_session_factory
from app.infrastructure.database.models import Base
from app.infrastructure.security.rate_limiter import limiter
from app.presentation.auth import router as auth_router
from app.presentation.chat import router as chat_router
from app.presentation.confirmations import router as confirmations_router
from app.presentation.jobs import router as jobs_router
from app.presentation.workspace import router as workspace_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    # On startup: create tables if they don't exist (dev convenience).
    # In production, use Alembic migrations exclusively.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # On shutdown: dispose engine pool.
    await engine.dispose()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="TalentCopilot API",
        description="Multi-tenant AI recruiting assistant platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── CORS ────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate Limiter ────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Routers ─────────────────────────────────────────────
    app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    app.include_router(chat_router, tags=["Chat"])
    app.include_router(confirmations_router, tags=["Confirmations"])
    app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
    app.include_router(workspace_router, tags=["Workspace"])

    @app.get("/health", tags=["System"])
    def get_health() -> dict:
        """Health check endpoint for orchestration tools."""
        return {"status": "ok"}

    return app


app = create_app()
