"""
Repository interfaces (ports) — abstract contracts for the domain.
Every method requires tenant_id as the first parameter to enforce isolation.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domain.entities import (
    Candidate,
    Confirmation,
    Job,
    Message,
    Repository,
    Session,
    SessionSummary,
    User,
)
from app.domain.enums import ConfirmationStatus, JobStatus, ToolName


class IUserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> Optional[User]:
        ...

    @abstractmethod
    async def get_by_id(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Optional[User]:
        ...

    @abstractmethod
    async def create(self, user: User) -> User:
        ...


class ISessionRepository(ABC):
    @abstractmethod
    async def create(self, session: Session) -> Session:
        ...

    @abstractmethod
    async def get_by_id(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> Optional[Session]:
        ...

    @abstractmethod
    async def list_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50
    ) -> List[Session]:
        ...

    @abstractmethod
    async def update_title(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, title: str
    ) -> None:
        ...


class IMessageRepository(ABC):
    @abstractmethod
    async def create(self, message: Message) -> Message:
        ...

    @abstractmethod
    async def get_recent(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, limit: int = 20
    ) -> List[Message]:
        ...

    @abstractmethod
    async def count(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> int:
        ...

    @abstractmethod
    async def get_range(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        offset: int,
        limit: int,
    ) -> List[Message]:
        ...


class ISessionSummaryRepository(ABC):
    @abstractmethod
    async def create(self, summary: SessionSummary) -> SessionSummary:
        ...

    @abstractmethod
    async def get_latest(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> Optional[SessionSummary]:
        ...


class IConfirmationRepository(ABC):
    @abstractmethod
    async def create(self, confirmation: Confirmation) -> Confirmation:
        ...

    @abstractmethod
    async def get_by_id(
        self, tenant_id: uuid.UUID, confirmation_id: uuid.UUID
    ) -> Optional[Confirmation]:
        ...

    @abstractmethod
    async def update_status(
        self,
        tenant_id: uuid.UUID,
        confirmation_id: uuid.UUID,
        status: ConfirmationStatus,
    ) -> None:
        ...

    @abstractmethod
    async def get_pending_for_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> List[Confirmation]:
        ...


class IJobRepository(ABC):
    @abstractmethod
    async def create(self, job: Job) -> Job:
        ...

    @abstractmethod
    async def get_by_id(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> Optional[Job]:
        ...

    @abstractmethod
    async def update_status(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        ...

    @abstractmethod
    async def list_for_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> List[Job]:
        ...


class ICandidateRepository(ABC):
    @abstractmethod
    async def create(self, candidate: Candidate) -> Candidate:
        ...

    @abstractmethod
    async def list_all(
        self, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[Candidate]:
        ...

    @abstractmethod
    async def get_by_id(
        self, tenant_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> Optional[Candidate]:
        ...


class IRepositoryRepo(ABC):
    """Repository for ingested GitHub repositories (named IRepositoryRepo to avoid
    collision with the pattern name)."""

    @abstractmethod
    async def create(self, repo: Repository) -> Repository:
        ...

    @abstractmethod
    async def get_by_url(
        self, tenant_id: uuid.UUID, repo_url: str
    ) -> Optional[Repository]:
        ...

    @abstractmethod
    async def list_all(
        self, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[Repository]:
        ...

    @abstractmethod
    async def upsert(self, repo: Repository) -> Repository:
        ...
