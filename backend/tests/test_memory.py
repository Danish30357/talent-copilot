"""
Tests for memory service: windowing and summarization trigger.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.application.memory_service import MemoryService
from app.domain.entities import Message, SessionSummary
from app.domain.enums import MessageRole
from tests.conftest import create_tenant_and_user


class TestMemoryWindowing:
    """Recent messages window is respected."""

    @pytest.mark.asyncio
    async def test_recent_messages_limit_applied(
        self, db_session, session_repo, message_repo, summary_repo,
        candidate_repo, repository_repo
    ):
        tid, uid = await create_tenant_and_user(db_session, "mem-win-org", "mw@x.com")
        sess_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid), user_id=str(uid),
            title="Memory test", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        # Add 30 messages
        for i in range(30):
            msg = Message(
                id=uuid.uuid4(), tenant_id=tid,
                session_id=sess_id, role=MessageRole.USER,
                content=f"Message {i}",
                created_at=datetime.utcnow(),
            )
            await message_repo.create(msg)
        await db_session.commit()

        svc = MemoryService(message_repo, summary_repo, candidate_repo, repository_repo)

        # Default window size is 20
        recent = await svc.get_recent_messages(tid, sess_id)
        assert len(recent) <= 20

    @pytest.mark.asyncio
    async def test_should_summarise_triggers_at_threshold(
        self, db_session, session_repo, message_repo, summary_repo,
        candidate_repo, repository_repo
    ):
        """should_summarise returns True when message count >= threshold."""
        tid, uid = await create_tenant_and_user(db_session, "summ-org", "sm@x.com")
        sess_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid), user_id=str(uid),
            title="Summary test", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = MemoryService(message_repo, summary_repo, candidate_repo, repository_repo)

        # Below threshold — should NOT summarise
        for i in range(5):
            msg = Message(
                id=uuid.uuid4(), tenant_id=tid,
                session_id=sess_id, role=MessageRole.USER,
                content=f"Msg {i}", created_at=datetime.utcnow(),
            )
            await message_repo.create(msg)
        await db_session.commit()

        should = await svc.should_summarise(tid, sess_id)
        assert should is False  # 5 messages, threshold is 50

    @pytest.mark.asyncio
    async def test_should_summarise_true_after_threshold(
        self, db_session, session_repo, message_repo, summary_repo,
        candidate_repo, repository_repo
    ):
        """Should summarise when messages since last summary >= threshold."""
        from app.config import get_settings
        settings = get_settings()

        tid, uid = await create_tenant_and_user(db_session, "summ2-org", "sm2@x.com")
        sess_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid), user_id=str(uid),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        # Add threshold number of messages
        for i in range(settings.summary_threshold):
            msg = Message(
                id=uuid.uuid4(), tenant_id=tid,
                session_id=sess_id, role=MessageRole.USER,
                content=f"Message {i}",
                created_at=datetime.utcnow(),
            )
            await message_repo.create(msg)
        await db_session.commit()

        svc = MemoryService(message_repo, summary_repo, candidate_repo, repository_repo)
        should = await svc.should_summarise(tid, sess_id)
        assert should is True

    @pytest.mark.asyncio
    async def test_workspace_context_includes_candidate(
        self, db_session, message_repo, summary_repo,
        candidate_repo, repository_repo
    ):
        """Workspace context text includes candidates by tenant."""
        from app.domain.entities import Candidate

        tid, _ = await create_tenant_and_user(db_session, "ctx-org", "ctx@x.com")

        cand = Candidate(
            id=uuid.uuid4(), tenant_id=tid,
            full_name="Jane Doe",
            email="jane@example.com",
            skills=["Python", "LangChain"],
            created_at=datetime.utcnow(),
        )
        await candidate_repo.create(cand)
        await db_session.commit()

        svc = MemoryService(message_repo, summary_repo, candidate_repo, repository_repo)
        ctx = await svc.get_workspace_context(tid)

        assert "Jane Doe" in ctx
        assert "Python" in ctx

    @pytest.mark.asyncio
    async def test_session_summary_stored_and_retrieved(
        self, db_session, session_repo, message_repo, summary_repo,
        candidate_repo, repository_repo
    ):
        """Session summary is correctly written and read back."""
        tid, uid = await create_tenant_and_user(db_session, "sumret-org", "sr@x.com")
        sess_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid), user_id=str(uid),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        summary = SessionSummary(
            id=uuid.uuid4(),
            tenant_id=tid,
            session_id=sess_id,
            summary_text="The user asked about Python skills.",
            message_count_at_summary=25,
            created_at=datetime.utcnow(),
        )
        await summary_repo.create(summary)
        await db_session.commit()

        svc = MemoryService(message_repo, summary_repo, candidate_repo, repository_repo)
        retrieved = await svc.get_session_summary(tid, sess_id)

        assert retrieved is not None
        assert "Python skills" in retrieved.summary_text
        assert retrieved.message_count_at_summary == 25
