"""
Domain entities — pure Python dataclasses, no ORM dependency.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.domain.enums import (
    ConfirmationStatus,
    JobStatus,
    MessageRole,
    ToolName,
)


@dataclass
class Tenant:
    id: uuid.UUID
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class User:
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    hashed_password: str
    full_name: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Session:
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    title: str = "New conversation"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Message:
    id: uuid.UUID
    tenant_id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SessionSummary:
    id: uuid.UUID
    tenant_id: uuid.UUID
    session_id: uuid.UUID
    summary_text: str
    message_count_at_summary: int
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Confirmation:
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID
    tool_name: ToolName
    tool_payload: Dict[str, Any] = field(default_factory=dict)
    tool_payload_hash: str = ""
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    decided_at: Optional[datetime] = None


@dataclass
class Job:
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID
    tool_name: ToolName
    status: JobStatus = JobStatus.QUEUED
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retries: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Candidate:
    id: uuid.UUID
    tenant_id: uuid.UUID
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    experience: List[Dict[str, Any]] = field(default_factory=list)
    education: List[Dict[str, Any]] = field(default_factory=list)
    projects: List[Dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""
    source_filename: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Repository:
    id: uuid.UUID
    tenant_id: uuid.UUID
    repo_url: str
    repo_name: str
    description: str = ""
    languages: List[str] = field(default_factory=list)
    structure: Dict[str, Any] = field(default_factory=dict)
    readme_content: str = ""
    code_snippets: List[Dict[str, Any]] = field(default_factory=list)
    ingested_at: datetime = field(default_factory=datetime.utcnow)
