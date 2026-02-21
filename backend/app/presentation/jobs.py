"""
Job status routes — poll background job progress.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.application.job_service import JobService
from app.dependencies import get_job_repo
from app.domain.exceptions import JobNotFound
from app.dto.responses import JobStatusResponse
from app.infrastructure.database.repositories import JobRepository
from app.infrastructure.security.auth_middleware import CurrentUser, get_current_user
from app.infrastructure.security.rate_limiter import limiter

router = APIRouter()


@router.get("/{job_id}/status", response_model=JobStatusResponse)
@limiter.limit("60/minute")
async def get_job_status(
    request: Request,
    job_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    job_repo: JobRepository = Depends(get_job_repo),
) -> JobStatusResponse:
    """Get the status of a background job."""
    service = JobService(job_repo)
    try:
        job = await service.get_status(user.tenant_id, job_id)
    except JobNotFound:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        id=job.id,
        tool_name=job.tool_name.value,
        status=job.status.value,
        result=job.result,
        error_message=job.error_message,
        retries=job.retries,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
