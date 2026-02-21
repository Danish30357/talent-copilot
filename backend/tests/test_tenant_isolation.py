"""
Tests for multi-tenant data isolation.

Critical requirement: Tenant A must NEVER see Tenant B's data.
Tests cover candidates, repositories, sessions, messages, and confirmations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.domain.entities import (
    Candidate, Confirmation, Message, Repository,
    Session as DomainSession,
)
from app.domain.enums import ConfirmationStatus, MessageRole, ToolName
from tests.conftest import create_tenant_and_user


class TestCandidateTenantIsolation:
    """Candidates are scoped by tenant_id."""

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b_candidates(
        self, db_session, candidate_repo
    ):
        tid_a, uid_a = await create_tenant_and_user(db_session, "tenant-a", "a@a.com")
        tid_b, uid_b = await create_tenant_and_user(db_session, "tenant-b", "b@b.com")

        # Create candidate for Tenant B
        candidate_b = Candidate(
            id=uuid.uuid4(),
            tenant_id=tid_b,
            full_name="Bob (Tenant B)",
            skills=["Python"],
            created_at=datetime.utcnow(),
        )
        await candidate_repo.create(candidate_b)
        await db_session.commit()

        # Tenant A should see NO candidates
        candidates_a = await candidate_repo.list_all(tid_a)
        assert len(candidates_a) == 0

        # Tenant B should see 1 candidate
        candidates_b = await candidate_repo.list_all(tid_b)
        assert len(candidates_b) == 1
        assert candidates_b[0].full_name == "Bob (Tenant B)"

    @pytest.mark.asyncio
    async def test_tenant_a_candidate_not_in_tenant_b(
        self, db_session, candidate_repo
    ):
        tid_a, _ = await create_tenant_and_user(db_session, "iso-a", "ia@x.com")
        tid_b, _ = await create_tenant_and_user(db_session, "iso-b", "ib@x.com")

        cand_a = Candidate(
            id=uuid.uuid4(), tenant_id=tid_a,
            full_name="Alice (A)", skills=["Go"],
            created_at=datetime.utcnow(),
        )
        await candidate_repo.create(cand_a)
        await db_session.commit()

        # Look up by ID should fail for Tenant B
        result = await candidate_repo.get_by_id(tid_b, cand_a.id)
        assert result is None

        # Correct tenant can retrieve it
        result = await candidate_repo.get_by_id(tid_a, cand_a.id)
        assert result is not None
        assert result.full_name == "Alice (A)"


class TestRepositoryTenantIsolation:
    """GitHub repos are scoped by tenant_id."""

    @pytest.mark.asyncio
    async def test_tenant_repos_isolated(self, db_session, repository_repo):
        tid_a, _ = await create_tenant_and_user(db_session, "repo-a", "ra@x.com")
        tid_b, _ = await create_tenant_and_user(db_session, "repo-b", "rb@x.com")

        repo_b = Repository(
            id=uuid.uuid4(),
            tenant_id=tid_b,
            repo_url="https://github.com/tenant-b/secret",
            repo_name="tenant-b/secret",
            ingested_at=datetime.utcnow(),
        )
        await repository_repo.create(repo_b)
        await db_session.commit()

        repos_a = await repository_repo.list_all(tid_a)
        assert len(repos_a) == 0

        repos_b = await repository_repo.list_all(tid_b)
        assert len(repos_b) == 1


class TestSessionTenantIsolation:
    """Sessions are scoped by tenant_id + user_id."""

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_tenant_sessions(
        self, db_session, session_repo
    ):
        tid_a, uid_a = await create_tenant_and_user(db_session, "sess-a", "sa@x.com")
        tid_b, uid_b = await create_tenant_and_user(db_session, "sess-b", "sb@x.com")

        sess_b = DomainSession(
            id=uuid.uuid4(), tenant_id=tid_b, user_id=uid_b,
            title="Secret session",
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        await session_repo.create(sess_b)
        await db_session.commit()

        sessions_a = await session_repo.list_for_user(tid_a, uid_a)
        assert len(sessions_a) == 0

        sessions_b = await session_repo.list_for_user(tid_b, uid_b)
        assert len(sessions_b) == 1


class TestMessageTenantIsolation:
    """Messages are scoped by tenant_id."""

    @pytest.mark.asyncio
    async def test_messages_isolated_per_tenant(
        self, db_session, session_repo, message_repo
    ):
        tid_a, uid_a = await create_tenant_and_user(db_session, "msg-a", "ma@x.com")
        tid_b, uid_b = await create_tenant_and_user(db_session, "msg-b", "mb@x.com")

        # Create sessions for both tenants
        sess_a_id = uuid.uuid4()
        sess_b_id = uuid.uuid4()

        sess_a = DomainSession(
            id=sess_a_id, tenant_id=tid_a, user_id=uid_a,
            title="A session", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        sess_b = DomainSession(
            id=sess_b_id, tenant_id=tid_b, user_id=uid_b,
            title="B session", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        await session_repo.create(sess_a)
        await session_repo.create(sess_b)
        await db_session.flush()

        # Add messages for Tenant B
        from app.domain.entities import Message
        msg_b = Message(
            id=uuid.uuid4(), tenant_id=tid_b,
            session_id=sess_b_id, role=MessageRole.USER,
            content="Tenant B secret message",
            created_at=datetime.utcnow(),
        )
        await message_repo.create(msg_b)
        await db_session.commit()

        # Tenant A should see no messages in its session
        msgs_a = await message_repo.get_recent(tid_a, sess_a_id)
        assert len(msgs_a) == 0

        # Tenant A cannot read Tenant B's session messages
        msgs_cross = await message_repo.get_recent(tid_a, sess_b_id)
        assert len(msgs_cross) == 0


class TestConfirmationTenantIsolation:
    """Confirmations are scoped by tenant_id."""

    @pytest.mark.asyncio
    async def test_confirmation_not_accessible_cross_tenant(
        self, db_session, confirmation_repo
    ):
        tid_a, uid_a = await create_tenant_and_user(db_session, "conf-a", "ca@x.com")
        tid_b, uid_b = await create_tenant_and_user(db_session, "conf-b", "cb@x.com")

        sess_id = uuid.uuid4()
        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid_b), user_id=str(uid_b),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        from app.application.confirmation_service import ConfirmationService
        svc = ConfirmationService(confirmation_repo)
        conf = await svc.request_confirmation(
            tenant_id=tid_b,
            user_id=uid_b,
            session_id=sess_id,
            tool_name=ToolName.GITHUB_INGESTION,
            tool_payload={"repo_url": "https://github.com/b/repo"},
        )
        await db_session.commit()

        # Tenant A should NOT be able to retrieve Tenant B's confirmation
        result = await confirmation_repo.get_by_id(tid_a, conf.id)
        assert result is None

        # Tenant B can retrieve it
        result = await confirmation_repo.get_by_id(tid_b, conf.id)
        assert result is not None
