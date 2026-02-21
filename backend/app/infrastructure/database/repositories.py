"""
Concrete repository implementations — every query is scoped by tenant_id.

Note: Models use String(36) for UUID PKs (portable across PostgreSQL/SQLite).
All repository methods convert uuid.UUID objects to str before querying.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession


def _str(value) -> str:
    """Convert UUID or similar to string for DB comparison."""
    return str(value) if value is not None else None


def _uuid(value) -> uuid.UUID:
    """Convert string ID back to uuid.UUID for domain entities."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value)) if value is not None else None

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
from app.domain.enums import ConfirmationStatus, JobStatus, MessageRole, ToolName
from app.domain.interfaces import (
    ICandidateRepository,
    IConfirmationRepository,
    IJobRepository,
    IMessageRepository,
    IRepositoryRepo,
    ISessionRepository,
    ISessionSummaryRepository,
    IUserRepository,
)
from app.infrastructure.database.models import (
    CandidateModel,
    ConfirmationModel,
    JobModel,
    MessageModel,
    RepositoryModel,
    SessionModel,
    SessionSummaryModel,
    UserModel,
)


# ────────────────────────────────────────────────────────────
# Mapping helpers
# ────────────────────────────────────────────────────────────

def _user_from_model(m: UserModel) -> User:
    return User(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), email=m.email,
        hashed_password=m.hashed_password, full_name=m.full_name,
        is_active=m.is_active, created_at=m.created_at,
    )


def _session_from_model(m: SessionModel) -> Session:
    return Session(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), user_id=_uuid(m.user_id),
        title=m.title, created_at=m.created_at, updated_at=m.updated_at,
    )


def _message_from_model(m: MessageModel) -> Message:
    return Message(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), session_id=_uuid(m.session_id),
        role=MessageRole(m.role), content=m.content,
        metadata=m.metadata_ or {}, created_at=m.created_at,
    )


def _summary_from_model(m: SessionSummaryModel) -> SessionSummary:
    return SessionSummary(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), session_id=_uuid(m.session_id),
        summary_text=m.summary_text,
        message_count_at_summary=m.message_count_at_summary,
        created_at=m.created_at,
    )


def _confirmation_from_model(m: ConfirmationModel) -> Confirmation:
    return Confirmation(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), user_id=_uuid(m.user_id),
        session_id=_uuid(m.session_id), tool_name=ToolName(m.tool_name),
        tool_payload=m.tool_payload or {}, tool_payload_hash=m.tool_payload_hash,
        status=ConfirmationStatus(m.status), created_at=m.created_at,
        decided_at=m.decided_at,
    )


def _job_from_model(m: JobModel) -> Job:
    return Job(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), user_id=_uuid(m.user_id),
        session_id=_uuid(m.session_id), tool_name=ToolName(m.tool_name),
        status=JobStatus(m.status), result=m.result,
        error_message=m.error_message, retries=m.retries,
        created_at=m.created_at, updated_at=m.updated_at,
    )


def _candidate_from_model(m: CandidateModel) -> Candidate:
    return Candidate(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), full_name=m.full_name,
        email=m.email, phone=m.phone, skills=m.skills or [],
        experience=m.experience or [], education=m.education or [],
        projects=m.projects or [], raw_text=m.raw_text,
        source_filename=m.source_filename, created_at=m.created_at,
    )


def _repo_from_model(m: RepositoryModel) -> Repository:
    return Repository(
        id=_uuid(m.id), tenant_id=_uuid(m.tenant_id), repo_url=m.repo_url,
        repo_name=m.repo_name, description=m.description,
        languages=m.languages or [], structure=m.structure or {},
        readme_content=m.readme_content,
        code_snippets=m.code_snippets or [], ingested_at=m.ingested_at,
    )


# ────────────────────────────────────────────────────────────
# User Repository
# ────────────────────────────────────────────────────────────
class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> Optional[User]:
        stmt = select(UserModel).where(
            and_(UserModel.tenant_id == _str(tenant_id), UserModel.email == email)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _user_from_model(row) if row else None

    async def get_by_id(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(UserModel).where(
            and_(UserModel.tenant_id == _str(tenant_id), UserModel.id == _str(user_id))
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _user_from_model(row) if row else None

    async def create(self, user: User) -> User:
        model = UserModel(
            id=_str(user.id), tenant_id=_str(user.tenant_id), email=user.email,
            hashed_password=user.hashed_password, full_name=user.full_name,
            is_active=user.is_active, created_at=user.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return user


# ────────────────────────────────────────────────────────────
# Session Repository
# ────────────────────────────────────────────────────────────
class SessionRepository(ISessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, sess: Session) -> Session:
        model = SessionModel(
            id=_str(sess.id), tenant_id=_str(sess.tenant_id), user_id=_str(sess.user_id),
            title=sess.title, created_at=sess.created_at, updated_at=sess.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return sess

    async def get_by_id(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> Optional[Session]:
        stmt = select(SessionModel).where(
            and_(SessionModel.tenant_id == _str(tenant_id), SessionModel.id == _str(session_id))
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _session_from_model(row) if row else None

    async def list_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50
    ) -> List[Session]:
        stmt = (
            select(SessionModel)
            .where(and_(SessionModel.tenant_id == _str(tenant_id), SessionModel.user_id == _str(user_id)))
            .order_by(SessionModel.updated_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_session_from_model(r) for r in result.scalars().all()]

    async def update_title(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, title: str
    ) -> None:
        stmt = (
            update(SessionModel)
            .where(and_(SessionModel.tenant_id == _str(tenant_id), SessionModel.id == _str(session_id)))
            .values(title=title, updated_at=datetime.utcnow())
        )
        await self._session.execute(stmt)


# ────────────────────────────────────────────────────────────
# Message Repository
# ────────────────────────────────────────────────────────────
class MessageRepository(IMessageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, message: Message) -> Message:
        model = MessageModel(
            id=_str(message.id), tenant_id=_str(message.tenant_id),
            session_id=_str(message.session_id),
            role=message.role.value, content=message.content,
            metadata_=message.metadata, created_at=message.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return message

    async def get_recent(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, limit: int = 20
    ) -> List[Message]:
        stmt = (
            select(MessageModel)
            .where(and_(MessageModel.tenant_id == _str(tenant_id), MessageModel.session_id == _str(session_id)))
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()  # chronological order
        return [_message_from_model(r) for r in rows]

    async def count(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> int:
        stmt = select(func.count(MessageModel.id)).where(
            and_(MessageModel.tenant_id == _str(tenant_id), MessageModel.session_id == _str(session_id))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_range(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, offset: int, limit: int
    ) -> List[Message]:
        stmt = (
            select(MessageModel)
            .where(and_(MessageModel.tenant_id == _str(tenant_id), MessageModel.session_id == _str(session_id)))
            .order_by(MessageModel.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_message_from_model(r) for r in result.scalars().all()]


# ────────────────────────────────────────────────────────────
# Session Summary Repository
# ────────────────────────────────────────────────────────────
class SessionSummaryRepository(ISessionSummaryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, summary: SessionSummary) -> SessionSummary:
        model = SessionSummaryModel(
            id=_str(summary.id), tenant_id=_str(summary.tenant_id),
            session_id=_str(summary.session_id),
            summary_text=summary.summary_text,
            message_count_at_summary=summary.message_count_at_summary,
            created_at=summary.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return summary

    async def get_latest(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> Optional[SessionSummary]:
        stmt = (
            select(SessionSummaryModel)
            .where(
                and_(
                    SessionSummaryModel.tenant_id == _str(tenant_id),
                    SessionSummaryModel.session_id == _str(session_id),
                )
            )
            .order_by(SessionSummaryModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _summary_from_model(row) if row else None


# ────────────────────────────────────────────────────────────
# Confirmation Repository
# ────────────────────────────────────────────────────────────
class ConfirmationRepository(IConfirmationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, confirmation: Confirmation) -> Confirmation:
        model = ConfirmationModel(
            id=_str(confirmation.id), tenant_id=_str(confirmation.tenant_id),
            user_id=_str(confirmation.user_id), session_id=_str(confirmation.session_id),
            tool_name=confirmation.tool_name.value, tool_payload=confirmation.tool_payload,
            tool_payload_hash=confirmation.tool_payload_hash,
            status=confirmation.status.value, created_at=confirmation.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return confirmation

    async def get_by_id(
        self, tenant_id: uuid.UUID, confirmation_id: uuid.UUID
    ) -> Optional[Confirmation]:
        stmt = select(ConfirmationModel).where(
            and_(ConfirmationModel.tenant_id == _str(tenant_id), ConfirmationModel.id == _str(confirmation_id))
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _confirmation_from_model(row) if row else None

    async def update_status(
        self, tenant_id: uuid.UUID, confirmation_id: uuid.UUID, status: ConfirmationStatus
    ) -> None:
        stmt = (
            update(ConfirmationModel)
            .where(
                and_(
                    ConfirmationModel.tenant_id == _str(tenant_id),
                    ConfirmationModel.id == _str(confirmation_id),
                )
            )
            .values(status=status.value, decided_at=datetime.utcnow())
        )
        await self._session.execute(stmt)

    async def get_pending_for_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> List[Confirmation]:
        stmt = (
            select(ConfirmationModel)
            .where(
                and_(
                    ConfirmationModel.tenant_id == _str(tenant_id),
                    ConfirmationModel.session_id == _str(session_id),
                    ConfirmationModel.status == "pending",
                )
            )
            .order_by(ConfirmationModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [_confirmation_from_model(r) for r in result.scalars().all()]


# ────────────────────────────────────────────────────────────
# Job Repository
# ────────────────────────────────────────────────────────────
class JobRepository(IJobRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, job: Job) -> Job:
        model = JobModel(
            id=_str(job.id), tenant_id=_str(job.tenant_id), user_id=_str(job.user_id),
            session_id=_str(job.session_id), tool_name=job.tool_name.value,
            status=job.status.value, retries=job.retries,
            created_at=job.created_at, updated_at=job.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return job

    async def get_by_id(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Optional[Job]:
        stmt = select(JobModel).where(
            and_(JobModel.tenant_id == _str(tenant_id), JobModel.id == _str(job_id))
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _job_from_model(row) if row else None

    async def update_status(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        values: Dict[str, Any] = {"status": status.value, "updated_at": datetime.utcnow()}
        if result is not None:
            values["result"] = result
        if error_message is not None:
            values["error_message"] = error_message
        stmt = (
            update(JobModel)
            .where(and_(JobModel.tenant_id == _str(tenant_id), JobModel.id == _str(job_id)))
            .values(**values)
        )
        await self._session.execute(stmt)

    async def list_for_session(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> List[Job]:
        stmt = (
            select(JobModel)
            .where(and_(JobModel.tenant_id == _str(tenant_id), JobModel.session_id == _str(session_id)))
            .order_by(JobModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [_job_from_model(r) for r in result.scalars().all()]


# ────────────────────────────────────────────────────────────
# Candidate Repository
# ────────────────────────────────────────────────────────────
class CandidateRepository(ICandidateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, candidate: Candidate) -> Candidate:
        model = CandidateModel(
            id=_str(candidate.id), tenant_id=_str(candidate.tenant_id),
            full_name=candidate.full_name, email=candidate.email,
            phone=candidate.phone, skills=candidate.skills,
            experience=candidate.experience, education=candidate.education,
            projects=candidate.projects, raw_text=candidate.raw_text,
            source_filename=candidate.source_filename, created_at=candidate.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return candidate

    async def list_all(
        self, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[Candidate]:
        stmt = (
            select(CandidateModel)
            .where(CandidateModel.tenant_id == _str(tenant_id))
            .order_by(CandidateModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_candidate_from_model(r) for r in result.scalars().all()]

    async def get_by_id(
        self, tenant_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> Optional[Candidate]:
        stmt = select(CandidateModel).where(
            and_(CandidateModel.tenant_id == _str(tenant_id), CandidateModel.id == _str(candidate_id))
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _candidate_from_model(row) if row else None


# ────────────────────────────────────────────────────────────
# Repository Repo (GitHub repos)
# ────────────────────────────────────────────────────────────
class RepositoryRepo(IRepositoryRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, repo: Repository) -> Repository:
        model = RepositoryModel(
            id=_str(repo.id), tenant_id=_str(repo.tenant_id), repo_url=repo.repo_url,
            repo_name=repo.repo_name, description=repo.description,
            languages=repo.languages, structure=repo.structure,
            readme_content=repo.readme_content, code_snippets=repo.code_snippets,
            ingested_at=repo.ingested_at,
        )
        self._session.add(model)
        await self._session.flush()
        return repo

    async def get_by_url(self, tenant_id: uuid.UUID, repo_url: str) -> Optional[Repository]:
        stmt = select(RepositoryModel).where(
            and_(RepositoryModel.tenant_id == _str(tenant_id), RepositoryModel.repo_url == repo_url)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _repo_from_model(row) if row else None

    async def list_all(
        self, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[Repository]:
        stmt = (
            select(RepositoryModel)
            .where(RepositoryModel.tenant_id == _str(tenant_id))
            .order_by(RepositoryModel.ingested_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_repo_from_model(r) for r in result.scalars().all()]

    async def upsert(self, repo: Repository) -> Repository:
        """
        Upsert a repository. Uses a portable approach: try create, update on conflict.
        For production PostgreSQL, this uses ON CONFLICT DO UPDATE.
        For SQLite in tests, it deletes and re-inserts.
        """
        existing = await self.get_by_url(repo.tenant_id, repo.repo_url)
        if existing:
            stmt = (
                update(RepositoryModel)
                .where(
                    and_(
                        RepositoryModel.tenant_id == _str(repo.tenant_id),
                        RepositoryModel.repo_url == repo.repo_url,
                    )
                )
                .values(
                    repo_name=repo.repo_name,
                    description=repo.description,
                    languages=repo.languages,
                    structure=repo.structure,
                    readme_content=repo.readme_content,
                    code_snippets=repo.code_snippets,
                    ingested_at=repo.ingested_at,
                )
            )
            await self._session.execute(stmt)
        else:
            await self.create(repo)
        await self._session.flush()
        return repo
