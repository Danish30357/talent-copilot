"""
Tests for job creation and status tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.application.job_service import JobService
from app.domain.enums import JobStatus, ToolName
from app.domain.exceptions import JobNotFound
from tests.conftest import create_tenant_and_user


class TestJobService:

    @pytest.mark.asyncio
    async def test_create_job_queued_status(self, db_session, job_repo):
        tid, uid = await create_tenant_and_user(db_session, "job-org", "j@x.com")
        sess_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid), user_id=str(uid),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = JobService(job_repo)
        job = await svc.create_job(tid, uid, sess_id, ToolName.GITHUB_INGESTION)
        await db_session.commit()

        assert job.status == JobStatus.QUEUED
        assert job.tenant_id == tid
        assert job.tool_name == ToolName.GITHUB_INGESTION

    @pytest.mark.asyncio
    async def test_get_job_status_returns_correct_state(self, db_session, job_repo):
        tid, uid = await create_tenant_and_user(db_session, "jobstat-org", "js@x.com")
        sess_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid), user_id=str(uid),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = JobService(job_repo)
        job = await svc.create_job(tid, uid, sess_id, ToolName.CV_PARSING)
        await db_session.commit()

        retrieved = await svc.get_status(tid, job.id)
        assert retrieved.id == job.id
        assert retrieved.status == JobStatus.QUEUED

    @pytest.mark.asyncio
    async def test_job_status_update_lifecycle(self, db_session, job_repo):
        """Job transitions through queued → running → completed."""
        tid, uid = await create_tenant_and_user(db_session, "joblife-org", "jl@x.com")
        sess_id = uuid.uuid4()

        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_id), tenant_id=str(tid), user_id=str(uid),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = JobService(job_repo)
        job = await svc.create_job(tid, uid, sess_id, ToolName.GITHUB_INGESTION)
        await db_session.commit()

        # Mark running
        await job_repo.update_status(tid, job.id, JobStatus.RUNNING)
        await db_session.commit()

        running_job = await svc.get_status(tid, job.id)
        assert running_job.status == JobStatus.RUNNING

        # Mark completed
        await job_repo.update_status(
            tid, job.id, JobStatus.COMPLETED,
            result={"repo_name": "owner/repo", "languages": ["Python"]},
        )
        await db_session.commit()

        completed_job = await svc.get_status(tid, job.id)
        assert completed_job.status == JobStatus.COMPLETED
        assert completed_job.result["repo_name"] == "owner/repo"

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_raises_not_found(self, db_session, job_repo):
        tid, _ = await create_tenant_and_user(db_session, "notfound-org", "nf@x.com")
        svc = JobService(job_repo)

        with pytest.raises(JobNotFound):
            await svc.get_status(tid, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_job_tenant_isolation(self, db_session, job_repo):
        """Tenant A cannot access Tenant B's job."""
        tid_a, uid_a = await create_tenant_and_user(db_session, "joba", "ja@x.com")
        tid_b, uid_b = await create_tenant_and_user(db_session, "jobb", "jb@x.com")

        sess_b = uuid.uuid4()
        from app.infrastructure.database.models import SessionModel
        db_session.add(SessionModel(id=str(sess_b), tenant_id=str(tid_b), user_id=str(uid_b),
            title="T", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        await db_session.flush()

        svc = JobService(job_repo)
        job_b = await svc.create_job(tid_b, uid_b, sess_b, ToolName.GITHUB_INGESTION)
        await db_session.commit()

        # Tenant A cannot find Tenant B's job
        with pytest.raises(JobNotFound):
            await svc.get_status(tid_a, job_b.id)
