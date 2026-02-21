"""
FastAPI dependency injection — wires repositories and services together.
"""

from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.connection import get_async_session
from app.infrastructure.database.repositories import (
    CandidateRepository,
    ConfirmationRepository,
    JobRepository,
    MessageRepository,
    RepositoryRepo,
    SessionRepository,
    SessionSummaryRepository,
    UserRepository,
)
from app.infrastructure.security.auth_middleware import CurrentUser, get_current_user


# ── Repository factories ───────────────────────────────────

def get_user_repo(session: AsyncSession = Depends(get_async_session)) -> UserRepository:
    return UserRepository(session)


def get_session_repo(session: AsyncSession = Depends(get_async_session)) -> SessionRepository:
    return SessionRepository(session)


def get_message_repo(session: AsyncSession = Depends(get_async_session)) -> MessageRepository:
    return MessageRepository(session)


def get_summary_repo(
    session: AsyncSession = Depends(get_async_session),
) -> SessionSummaryRepository:
    return SessionSummaryRepository(session)


def get_confirmation_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ConfirmationRepository:
    return ConfirmationRepository(session)


def get_job_repo(session: AsyncSession = Depends(get_async_session)) -> JobRepository:
    return JobRepository(session)


def get_candidate_repo(session: AsyncSession = Depends(get_async_session)) -> CandidateRepository:
    return CandidateRepository(session)


def get_repository_repo(session: AsyncSession = Depends(get_async_session)) -> RepositoryRepo:
    return RepositoryRepo(session)


# ── Convenience re-exports ─────────────────────────────────

def get_tenant_id(user: CurrentUser = Depends(get_current_user)) -> uuid.UUID:
    """Extract tenant_id from validated token."""
    return user.tenant_id
