"""
Test fixtures and shared setup for TalentCopilot tests.

Uses SQLite in-memory for the DB and mocks external services.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ── Test database (SQLite in-memory) ───────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# ── Override settings before importing app ─────────────────
import os
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///./test.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.infrastructure.database.models import Base
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
from app.domain.entities import (
    Candidate, Confirmation, Job, Message, Repository,
    Session as DomainSession, SessionSummary, User,
)
from app.domain.enums import (
    ConfirmationStatus, JobStatus, MessageRole, ToolName,
)
from app.infrastructure.security.jwt_handler import JWTHandler

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Async test event loop ───────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Test database engine ────────────────────────────────────
@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        # SQLite doesn't support ARRAY or UUID natively — use JSON fallback ORM
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Fresh DB session per test."""
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


# ── Repository fixtures ─────────────────────────────────────
@pytest.fixture
def user_repo(db_session):
    return UserRepository(db_session)


@pytest.fixture
def session_repo(db_session):
    return SessionRepository(db_session)


@pytest.fixture
def message_repo(db_session):
    return MessageRepository(db_session)


@pytest.fixture
def summary_repo(db_session):
    return SessionSummaryRepository(db_session)


@pytest.fixture
def confirmation_repo(db_session):
    return ConfirmationRepository(db_session)


@pytest.fixture
def job_repo(db_session):
    return JobRepository(db_session)


@pytest.fixture
def candidate_repo(db_session):
    return CandidateRepository(db_session)


@pytest.fixture
def repository_repo(db_session):
    return RepositoryRepo(db_session)


@pytest.fixture
def jwt_handler():
    return JWTHandler()


def make_token(jwt_handler, user_id, tenant_id):
    return jwt_handler.create_access_token(user_id, tenant_id)

# ── Seed data helpers ───────────────────────────────────────
async def create_tenant_and_user(db_session, tenant_name="test-org", email="user@test.com"):
    """Create a tenant+user combo for testing."""
    from app.infrastructure.database.models import TenantModel, UserModel

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    tenant = TenantModel(id=str(tenant_id), name=tenant_name)
    db_session.add(tenant)
    await db_session.flush()

    user = UserModel(
        id=str(user_id),
        tenant_id=str(tenant_id),
        email=email,
        # Use a hardcoded dummy hash to avoid passlib/bcrypt >4.0 incompatibilities in tests
        hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQqiRQYq",
        full_name="Test User",
    )
    db_session.add(user)
    await db_session.flush()

    return tenant_id, user_id
