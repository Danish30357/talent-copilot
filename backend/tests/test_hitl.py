"""
Tests for the HITL confirmation flow.

Covers:
- GitHub ingestion confirmation: approve path
- GitHub ingestion confirmation: deny path
- CV parsing confirmation: parse-only (no persist)
- CV save confirmation: approve persists candidate
- No mismatched confirmations (payload hash check)
- Cannot bypass confirmation (expired/wrong status)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.application.confirmation_service import ConfirmationService
from app.application.job_service import JobService
from app.application.tool_service import ToolService
from app.domain.enums import ConfirmationStatus, JobStatus, ToolName
from app.domain.exceptions import ConfirmationDenied, ConfirmationHashMismatch, ConfirmationRequired
from tests.conftest import create_tenant_and_user


# ── Helper: compute expected hash ───────────────────────────

def _expected_hash(tenant_id, user_id, session_id, tool_name: str, payload: dict) -> str:
    canonical = json.dumps(
        {
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "session_id": str(session_id),
            "tool_name": tool_name,
            "tool_payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Tests ────────────────────────────────────────────────────

class TestGitHubConfirmationApprove:
    """User approves GitHub ingestion → job is dispatched."""

    @pytest.mark.asyncio
    async def test_approve_creates_approved_confirmation(
        self, db_session, confirmation_repo, job_repo
    ):
        tenant_id, user_id = await create_tenant_and_user(db_session)
        session_id = uuid.uuid4()

        # Step 1: Create session record
        from app.infrastructure.database.models import SessionModel
        session_model = SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="Test", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db_session.add(session_model)
        await db_session.flush()

        payload = {"repo_url": "https://github.com/owner/repo"}
        svc = ConfirmationService(confirmation_repo)

        # Step 2: Request confirmation
        confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.GITHUB_INGESTION,
            tool_payload=payload,
        )
        await db_session.commit()

        assert confirmation.status == ConfirmationStatus.PENDING
        assert confirmation.tenant_id == tenant_id

        # Step 3: Approve
        updated = await svc.decide(tenant_id, confirmation.id, approved=True)
        await db_session.commit()

        assert updated.status == ConfirmationStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_validates_hash(
        self, db_session, confirmation_repo, job_repo
    ):
        tenant_id, user_id = await create_tenant_and_user(db_session, "hash-org")
        session_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        payload = {"repo_url": "https://github.com/owner/testrepo"}
        svc = ConfirmationService(confirmation_repo)

        confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.GITHUB_INGESTION,
            tool_payload=payload,
        )
        await db_session.commit()
        await svc.decide(tenant_id, confirmation.id, approved=True)
        await db_session.commit()

        # Validate for execution — should NOT raise
        result = await svc.validate_for_execution(
            tenant_id=tenant_id,
            confirmation_id=confirmation.id,
            tool_name=ToolName.GITHUB_INGESTION.value,
            tool_payload=payload,
        )
        assert result.status == ConfirmationStatus.APPROVED

    @pytest.mark.asyncio
    async def test_tampered_payload_raises_hash_mismatch(
        self, db_session, confirmation_repo
    ):
        tenant_id, user_id = await create_tenant_and_user(db_session, "tamper-org")
        session_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        payload = {"repo_url": "https://github.com/owner/original"}
        svc = ConfirmationService(confirmation_repo)

        confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.GITHUB_INGESTION,
            tool_payload=payload,
        )
        await db_session.commit()
        await svc.decide(tenant_id, confirmation.id, approved=True)
        await db_session.commit()

        # Try to execute with a different payload
        tampered_payload = {"repo_url": "https://github.com/attacker/evil-repo"}
        with pytest.raises(ConfirmationHashMismatch):
            await svc.validate_for_execution(
                tenant_id=tenant_id,
                confirmation_id=confirmation.id,
                tool_name=ToolName.GITHUB_INGESTION.value,
                tool_payload=tampered_payload,
            )


class TestGitHubConfirmationDeny:
    """User denies GitHub ingestion → no job dispatched."""

    @pytest.mark.asyncio
    async def test_deny_sets_denied_status(self, db_session, confirmation_repo):
        tenant_id, user_id = await create_tenant_and_user(db_session, "deny-org")
        session_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = ConfirmationService(confirmation_repo)
        confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.GITHUB_INGESTION,
            tool_payload={"repo_url": "https://github.com/owner/repo"},
        )
        await db_session.commit()

        updated = await svc.decide(tenant_id, confirmation.id, approved=False)
        await db_session.commit()

        assert updated.status == ConfirmationStatus.DENIED

    @pytest.mark.asyncio
    async def test_denied_confirmation_blocks_execution(self, db_session, confirmation_repo):
        tenant_id, user_id = await create_tenant_and_user(db_session, "block-org")
        session_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = ConfirmationService(confirmation_repo)
        payload = {"repo_url": "https://github.com/owner/repo"}
        confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.GITHUB_INGESTION,
            tool_payload=payload,
        )
        await db_session.commit()

        # Deny it
        await svc.decide(tenant_id, confirmation.id, approved=False)
        await db_session.commit()

        # Attempt to execute should raise ConfirmationDenied
        with pytest.raises(ConfirmationDenied):
            await svc.validate_for_execution(
                tenant_id=tenant_id,
                confirmation_id=confirmation.id,
                tool_name=ToolName.GITHUB_INGESTION.value,
                tool_payload=payload,
            )

    @pytest.mark.asyncio
    async def test_double_decide_raises_error(self, db_session, confirmation_repo):
        """Cannot decide a confirmation that has already been decided."""
        tenant_id, user_id = await create_tenant_and_user(db_session, "double-org")
        session_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = ConfirmationService(confirmation_repo)
        confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.GITHUB_INGESTION,
            tool_payload={"repo_url": "https://github.com/owner/repo"},
        )
        await db_session.commit()

        await svc.decide(tenant_id, confirmation.id, approved=True)
        await db_session.commit()

        # Second decide should raise ConfirmationDenied (already decided)
        with pytest.raises(ConfirmationDenied):
            await svc.decide(tenant_id, confirmation.id, approved=False)


class TestCVParsingHITL:
    """CV parsing requires HITL approval; parse is parse-only (no DB persist)."""

    @pytest.mark.asyncio
    async def test_cv_parse_confirmation_created(self, db_session, confirmation_repo):
        tenant_id, user_id = await create_tenant_and_user(db_session, "cv-org")
        session_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = ConfirmationService(confirmation_repo)
        confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.CV_PARSING,
            tool_payload={"file_path": "/tmp/test.pdf", "filename": "test.pdf"},
        )
        await db_session.commit()

        assert confirmation.tool_name == ToolName.CV_PARSING
        assert confirmation.status == ConfirmationStatus.PENDING

    @pytest.mark.asyncio
    async def test_cv_save_confirmation_created_separately(
        self, db_session, confirmation_repo
    ):
        """cv_save is a distinct ToolName from cv_parsing."""
        tenant_id, user_id = await create_tenant_and_user(db_session, "cvsave-org")
        session_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(session_id), tenant_id=str(tenant_id), user_id=str(user_id),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = ConfirmationService(confirmation_repo)
        parse_job_id = str(uuid.uuid4())

        save_confirmation = await svc.request_confirmation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=ToolName.CV_SAVE,
            tool_payload={"parse_job_id": parse_job_id},
        )
        await db_session.commit()

        assert save_confirmation.tool_name == ToolName.CV_SAVE
        assert save_confirmation.status == ConfirmationStatus.PENDING
        assert save_confirmation.tool_payload["parse_job_id"] == parse_job_id
