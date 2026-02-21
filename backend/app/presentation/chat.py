"""
Chat routes — send messages, get history, list sessions.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.chat_service import ChatService
from app.dependencies import (
    get_candidate_repo,
    get_confirmation_repo,
    get_job_repo,
    get_message_repo,
    get_repository_repo,
    get_session_repo,
    get_summary_repo,
)
from app.dto.requests import ChatMessageRequest
from app.dto.responses import ChatResponse, MessageOut, SessionOut
from app.infrastructure.database.connection import get_async_session
from app.infrastructure.database.repositories import (
    CandidateRepository,
    ConfirmationRepository,
    JobRepository,
    MessageRepository,
    RepositoryRepo,
    SessionRepository,
    SessionSummaryRepository,
)
from app.infrastructure.security.auth_middleware import CurrentUser, get_current_user
from app.infrastructure.security.rate_limiter import limiter

router = APIRouter()


def _get_chat_service(
    session_repo: SessionRepository = Depends(get_session_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    summary_repo: SessionSummaryRepository = Depends(get_summary_repo),
    confirmation_repo: ConfirmationRepository = Depends(get_confirmation_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    candidate_repo: CandidateRepository = Depends(get_candidate_repo),
    repository_repo: RepositoryRepo = Depends(get_repository_repo),
) -> ChatService:
    return ChatService(
        session_repo, message_repo, summary_repo,
        confirmation_repo, job_repo, candidate_repo, repository_repo,
    )


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def send_message(
    request: Request,
    body: ChatMessageRequest,
    user: CurrentUser = Depends(get_current_user),
    chat_service: ChatService = Depends(_get_chat_service),
) -> ChatResponse:
    """Send a message and receive the AI response."""
    result = await chat_service.handle_message(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=body.session_id,
        content=body.content,
    )
    return ChatResponse(
        session_id=uuid.UUID(result["session_id"]),
        message=MessageOut(
            id=uuid.UUID(result["message"]["id"]),
            role=result["message"]["role"],
            content=result["message"]["content"],
            metadata=result["message"]["metadata"],
            created_at=result["message"]["created_at"],
        ),
        confirmation_required=result.get("confirmation_required", False),
        confirmation_id=(
            uuid.UUID(result["confirmation_id"]) if result.get("confirmation_id") else None
        ),
        confirmation_details=result.get("confirmation_details"),
    )


@router.get("/chat/sessions/{session_id}/history")
@limiter.limit("60/minute")
async def get_history(
    request: Request,
    session_id: uuid.UUID,
    offset: int = 0,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
    chat_service: ChatService = Depends(_get_chat_service),
):
    """Get paginated message history for a session."""
    messages = await chat_service.get_history(
        tenant_id=user.tenant_id,
        session_id=session_id,
        offset=offset,
        limit=min(limit, 100),
    )
    return [
        MessageOut(
            id=m.id, role=m.role.value, content=m.content,
            metadata=m.metadata, created_at=m.created_at,
        )
        for m in messages
    ]


@router.get("/chat/sessions")
@limiter.limit("30/minute")
async def list_sessions(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    chat_service: ChatService = Depends(_get_chat_service),
):
    """List all sessions for the current user."""
    sessions = await chat_service.list_sessions(user.tenant_id, user.user_id)
    return [
        SessionOut(
            id=s.id, title=s.title,
            created_at=s.created_at, updated_at=s.updated_at,
        )
        for s in sessions
    ]
