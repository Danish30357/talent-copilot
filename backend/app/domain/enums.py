"""
Domain enumerations for TalentCopilot.
"""

from __future__ import annotations

import enum


class MessageRole(str, enum.Enum):
    """Who authored a message."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConfirmationStatus(str, enum.Enum):
    """Lifecycle of a confirmation request."""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class JobStatus(str, enum.Enum):
    """Background job lifecycle."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class GraphState(str, enum.Enum):
    """Explicit states in the LangGraph state machine."""
    CONVERSATION = "conversation"
    TOOL_DECISION = "tool_decision"
    CONFIRMATION_PENDING = "confirmation_pending"
    TOOL_EXECUTION = "tool_execution"
    RESPONSE_GENERATION = "response_generation"


class ToolName(str, enum.Enum):
    """Registered tool identifiers."""
    GITHUB_INGESTION = "github_ingestion"
    CV_PARSING = "cv_parsing"
    CV_SAVE = "cv_save"  # HITL-gated save after parsing
