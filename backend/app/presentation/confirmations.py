"""
Confirmation routes — approve or deny tool execution requests.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.confirmation_service import ConfirmationService
from app.application.tool_service import ToolService
from app.dependencies import get_confirmation_repo, get_job_repo
from app.domain.enums import ConfirmationStatus, ToolName
from app.domain.exceptions import (
    ConfirmationDenied,
    ConfirmationHashMismatch,
    ConfirmationRequired,
)
from app.dto.requests import ConfirmationDecisionRequest
from app.dto.responses import ConfirmationDecisionResponse, ConfirmationResponse
from app.infrastructure.database.repositories import ConfirmationRepository, JobRepository
from app.infrastructure.security.auth_middleware import CurrentUser, get_current_user
from app.infrastructure.security.rate_limiter import limiter

router = APIRouter()


@router.get("/confirmations/{confirmation_id}", response_model=ConfirmationResponse)
@limiter.limit("60/minute")
async def get_confirmation(
    request: Request,
    confirmation_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    confirmation_repo: ConfirmationRepository = Depends(get_confirmation_repo),
) -> ConfirmationResponse:
    """Get details of a confirmation request."""
    service = ConfirmationService(confirmation_repo)
    confirmation = await confirmation_repo.get_by_id(user.tenant_id, confirmation_id)
    if confirmation is None:
        raise HTTPException(status_code=404, detail="Confirmation not found")

    return ConfirmationResponse(
        id=confirmation.id,
        tool_name=confirmation.tool_name.value,
        tool_payload=confirmation.tool_payload,
        status=confirmation.status.value,
        created_at=confirmation.created_at,
        decided_at=confirmation.decided_at,
    )


@router.post("/confirm", response_model=ConfirmationDecisionResponse)
@limiter.limit("10/minute")
async def decide_confirmation(
    request: Request,
    body: ConfirmationDecisionRequest,
    user: CurrentUser = Depends(get_current_user),
    confirmation_repo: ConfirmationRepository = Depends(get_confirmation_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> ConfirmationDecisionResponse:
    """
    Approve or deny a tool confirmation.
    If approved, the tool is dispatched as a background job.
    """
    confirmation_service = ConfirmationService(confirmation_repo)

    try:
        confirmation = await confirmation_service.decide(
            tenant_id=user.tenant_id,
            confirmation_id=body.confirmation_id,
            approved=body.approved,
        )
    except ConfirmationDenied:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Confirmation already decided",
        )
    except ConfirmationRequired:
        raise HTTPException(status_code=404, detail="Confirmation not found")

    if not body.approved:
        return ConfirmationDecisionResponse(
            id=confirmation.id,
            status=ConfirmationStatus.DENIED.value,
        )

    # Approved → dispatch tool
    tool_service = ToolService(confirmation_repo, job_repo)
    try:
        result = await tool_service.execute_tool_after_approval(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            session_id=confirmation.session_id,
            confirmation_id=confirmation.id,
            tool_name=confirmation.tool_name,
            tool_payload=confirmation.tool_payload,
        )
        return ConfirmationDecisionResponse(
            id=confirmation.id,
            status=ConfirmationStatus.APPROVED.value,
            tool_result=result,
            job_id=uuid.UUID(result["job_id"]),
        )
    except ConfirmationHashMismatch:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Confirmation payload hash mismatch — possible tampering",
        )
    except ConfirmationDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Confirmation was denied",
        )
