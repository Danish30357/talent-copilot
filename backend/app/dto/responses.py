"""
Pydantic response models — serialise only what the client needs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Auth ────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ── Chat ────────────────────────────────────────────────────

class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    metadata: Dict[str, Any] = {}
    created_at: datetime


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    message: MessageOut
    confirmation_required: bool = False
    confirmation_id: Optional[uuid.UUID] = None
    confirmation_details: Optional[Dict[str, Any]] = None


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


# ── Confirmation ────────────────────────────────────────────

class ConfirmationResponse(BaseModel):
    id: uuid.UUID
    tool_name: str
    tool_payload: Dict[str, Any]
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None


class ConfirmationDecisionResponse(BaseModel):
    id: uuid.UUID
    status: str
    tool_result: Optional[Dict[str, Any]] = None
    job_id: Optional[uuid.UUID] = None


# ── Job ─────────────────────────────────────────────────────

class JobStatusResponse(BaseModel):
    id: uuid.UUID
    tool_name: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retries: int
    created_at: datetime
    updated_at: datetime


# ── Workspace ───────────────────────────────────────────────

class CandidateResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    skills: List[str]
    experience: List[Dict[str, Any]]
    education: List[Dict[str, Any]]
    projects: List[Dict[str, Any]]
    source_filename: str
    created_at: datetime


class RepositoryResponse(BaseModel):
    id: uuid.UUID
    repo_url: str
    repo_name: str
    description: str
    languages: List[str]
    ingested_at: datetime
