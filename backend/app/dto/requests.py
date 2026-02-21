"""
Pydantic request models — strict input validation at the API boundary.
"""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)
    tenant_name: str = Field(..., min_length=1, max_length=255)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChatMessageRequest(BaseModel):
    session_id: Optional[uuid.UUID] = None  # None = create new session
    content: str = Field(..., min_length=1, max_length=10000)


class ConfirmationDecisionRequest(BaseModel):
    confirmation_id: uuid.UUID
    approved: bool


class GitHubIngestRequest(BaseModel):
    repo_url: str = Field(..., max_length=2048)

    @field_validator("repo_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith("https://github.com/"):
            raise ValueError("Only public GitHub HTTPS URLs are allowed")
        parts = v.replace("https://github.com/", "").split("/")
        if len(parts) < 2:
            raise ValueError("URL must be in format https://github.com/owner/repo")
        return v


class CVUploadMetadata(BaseModel):
    session_id: uuid.UUID
