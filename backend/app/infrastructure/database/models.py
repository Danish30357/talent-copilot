"""
SQLAlchemy ORM models — all tables include tenant_id with appropriate indexes.

Notes on portability:
- UUID columns use String(36) so tests can run against SQLite.
- Array columns use JSON so they work on both PostgreSQL and SQLite.
- In production with PostgreSQL, SQLAlchemy automatically uses native JSON.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

# Use String(36) for UUIDs — works with both PostgreSQL and SQLite
_UUID = String(36)


class Base(DeclarativeBase):
    pass


# ────────────────────────────────────────────────────────────
# Tenants
# ────────────────────────────────────────────────────────────
class TenantModel(Base):
    __tablename__ = "tenants"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("UserModel", back_populates="tenant", cascade="all, delete-orphan")


# ────────────────────────────────────────────────────────────
# Users
# ────────────────────────────────────────────────────────────
class UserModel(Base):
    __tablename__ = "users"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email = Column(String(320), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), default="")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("TenantModel", back_populates="users")
    sessions = relationship("SessionModel", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        Index("ix_users_tenant_id", "tenant_id"),
    )


# ────────────────────────────────────────────────────────────
# Sessions
# ────────────────────────────────────────────────────────────
class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        _UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(500), default="New conversation")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("UserModel", back_populates="sessions")
    messages = relationship("MessageModel", back_populates="session", cascade="all, delete-orphan")
    summaries = relationship(
        "SessionSummaryModel", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_sessions_tenant_id", "tenant_id"),
        Index("ix_sessions_user_id", "user_id"),
    )


# ────────────────────────────────────────────────────────────
# Messages
# ────────────────────────────────────────────────────────────
class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    session_id = Column(
        _UUID, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(
        Enum("user", "assistant", "system", "tool", name="message_role_enum"),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("SessionModel", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_tenant_id", "tenant_id"),
        Index("ix_messages_session_id", "session_id"),
        Index("ix_messages_created_at", "created_at"),
    )


# ────────────────────────────────────────────────────────────
# Session Summaries
# ────────────────────────────────────────────────────────────
class SessionSummaryModel(Base):
    __tablename__ = "session_summaries"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    session_id = Column(
        _UUID, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    summary_text = Column(Text, nullable=False)
    message_count_at_summary = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("SessionModel", back_populates="summaries")

    __table_args__ = (
        Index("ix_session_summaries_tenant_id", "tenant_id"),
        Index("ix_session_summaries_session_id", "session_id"),
    )


# ────────────────────────────────────────────────────────────
# Confirmations
# ────────────────────────────────────────────────────────────
class ConfirmationModel(Base):
    __tablename__ = "confirmations"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        _UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id = Column(
        _UUID, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    tool_name = Column(String(100), nullable=False)
    tool_payload = Column(JSON, default=dict)
    tool_payload_hash = Column(String(64), nullable=False)  # SHA-256 hex
    status = Column(
        Enum("pending", "approved", "denied", "expired", name="confirmation_status_enum"),
        default="pending",
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_confirmations_tenant_id", "tenant_id"),
        Index("ix_confirmations_session_id", "session_id"),
        Index("ix_confirmations_status", "status"),
    )


# ────────────────────────────────────────────────────────────
# Jobs
# ────────────────────────────────────────────────────────────
class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        _UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id = Column(
        _UUID, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    tool_name = Column(String(100), nullable=False)
    status = Column(
        Enum("queued", "running", "completed", "failed", "retrying", name="job_status_enum"),
        default="queued",
        nullable=False,
    )
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    retries = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_jobs_tenant_id", "tenant_id"),
        Index("ix_jobs_session_id", "session_id"),
        Index("ix_jobs_status", "status"),
    )


# ────────────────────────────────────────────────────────────
# Candidates
# ────────────────────────────────────────────────────────────
class CandidateModel(Base):
    __tablename__ = "candidates"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    full_name = Column(String(255), nullable=False)
    email = Column(String(320), nullable=True)
    phone = Column(String(50), nullable=True)
    skills = Column(JSON, default=list)       # stored as JSON array (portable)
    experience = Column(JSON, default=list)
    education = Column(JSON, default=list)
    projects = Column(JSON, default=list)
    raw_text = Column(Text, default="")
    source_filename = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_candidates_tenant_id", "tenant_id"),)


# ────────────────────────────────────────────────────────────
# Repositories (Ingested GitHub repos)
# ────────────────────────────────────────────────────────────
class RepositoryModel(Base):
    __tablename__ = "repositories"

    id = Column(_UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(
        _UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    repo_url = Column(String(2048), nullable=False)
    repo_name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    languages = Column(JSON, default=list)    # stored as JSON array (portable)
    structure = Column(JSON, default=dict)
    readme_content = Column(Text, default="")
    code_snippets = Column(JSON, default=list)
    ingested_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_url", name="uq_repo_tenant_url"),
        Index("ix_repositories_tenant_id", "tenant_id"),
    )
