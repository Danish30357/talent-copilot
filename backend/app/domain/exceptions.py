"""
Domain-specific exceptions.
"""

from __future__ import annotations

import uuid


class TalentCopilotError(Exception):
    """Base exception for the platform."""


class TenantAccessDenied(TalentCopilotError):
    def __init__(self, tenant_id: uuid.UUID, resource: str = "resource"):
        super().__init__(f"Tenant {tenant_id} denied access to {resource}")
        self.tenant_id = tenant_id


class ConfirmationRequired(TalentCopilotError):
    """Raised when a tool requires user confirmation before execution."""

    def __init__(self, confirmation_id: uuid.UUID, tool_name: str):
        super().__init__(
            f"Confirmation {confirmation_id} required for tool '{tool_name}'"
        )
        self.confirmation_id = confirmation_id
        self.tool_name = tool_name


class ConfirmationDenied(TalentCopilotError):
    def __init__(self, confirmation_id: uuid.UUID):
        super().__init__(f"Confirmation {confirmation_id} was denied")
        self.confirmation_id = confirmation_id


class ConfirmationHashMismatch(TalentCopilotError):
    """The payload hash does not match — possible tampering or replay."""

    def __init__(self, confirmation_id: uuid.UUID):
        super().__init__(
            f"Confirmation {confirmation_id} payload hash mismatch (possible replay)"
        )
        self.confirmation_id = confirmation_id


class ConfirmationExpired(TalentCopilotError):
    def __init__(self, confirmation_id: uuid.UUID):
        super().__init__(f"Confirmation {confirmation_id} has expired")
        self.confirmation_id = confirmation_id


class JobNotFound(TalentCopilotError):
    def __init__(self, job_id: uuid.UUID):
        super().__init__(f"Job {job_id} not found")
        self.job_id = job_id


class SessionNotFound(TalentCopilotError):
    def __init__(self, session_id: uuid.UUID):
        super().__init__(f"Session {session_id} not found")
        self.session_id = session_id


class InvalidCredentials(TalentCopilotError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class FileValidationError(TalentCopilotError):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail
