"""
Job service — dispatches background tasks and tracks job lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from app.domain.entities import Job
from app.domain.enums import JobStatus, ToolName
from app.domain.exceptions import JobNotFound
from app.domain.interfaces import IJobRepository


class JobService:
    """Create jobs, dispatch to Celery, and poll status."""

    def __init__(self, job_repo: IJobRepository) -> None:
        self._repo = job_repo

    async def create_job(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        tool_name: ToolName,
    ) -> Job:
        job = Job(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            status=JobStatus.QUEUED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        return await self._repo.create(job)

    async def get_status(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Job:
        job = await self._repo.get_by_id(tenant_id, job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    async def mark_running(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
        await self._repo.update_status(tenant_id, job_id, JobStatus.RUNNING)

    async def mark_completed(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self._repo.update_status(tenant_id, job_id, JobStatus.COMPLETED, result=result)

    async def mark_failed(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, error_message: str
    ) -> None:
        await self._repo.update_status(
            tenant_id, job_id, JobStatus.FAILED, error_message=error_message
        )

    async def list_for_session(self, tenant_id: uuid.UUID, session_id: uuid.UUID):
        return await self._repo.list_for_session(tenant_id, session_id)
