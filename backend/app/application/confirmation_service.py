"""
Confirmation service — cryptographically ties tool execution to user approval.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict

from app.domain.entities import Confirmation
from app.domain.enums import ConfirmationStatus, ToolName
from app.domain.exceptions import (
    ConfirmationDenied,
    ConfirmationHashMismatch,
    ConfirmationRequired,
)
from app.domain.interfaces import IConfirmationRepository


class ConfirmationService:
    """Manages HITL confirmation lifecycle."""

    def __init__(self, confirmation_repo: IConfirmationRepository) -> None:
        self._repo = confirmation_repo

    @staticmethod
    def compute_payload_hash(
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        tool_name: str,
        tool_payload: Dict[str, Any],
    ) -> str:
        """
        SHA-256 of the canonical JSON representation, scoped to
        tenant + user + session + tool + payload.
        This prevents:
          - Cross-tenant replays
          - Cross-session replays
          - Payload tampering after confirmation
        """
        canonical = json.dumps(
            {
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "session_id": str(session_id),
                "tool_name": tool_name,
                "tool_payload": tool_payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def request_confirmation(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        tool_name: ToolName,
        tool_payload: Dict[str, Any],
    ) -> Confirmation:
        """Create a pending confirmation record."""
        payload_hash = self.compute_payload_hash(
            tenant_id, user_id, session_id, tool_name.value, tool_payload
        )
        confirmation = Confirmation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_payload=tool_payload,
            tool_payload_hash=payload_hash,
            status=ConfirmationStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        return await self._repo.create(confirmation)

    async def decide(
        self,
        tenant_id: uuid.UUID,
        confirmation_id: uuid.UUID,
        approved: bool,
    ) -> Confirmation:
        """
        Approve or deny a confirmation.
        Returns the updated confirmation entity.
        """
        confirmation = await self._repo.get_by_id(tenant_id, confirmation_id)
        if confirmation is None:
            raise ConfirmationRequired(confirmation_id, "unknown")

        if confirmation.status != ConfirmationStatus.PENDING:
            raise ConfirmationDenied(confirmation_id)  # already decided

        new_status = ConfirmationStatus.APPROVED if approved else ConfirmationStatus.DENIED
        await self._repo.update_status(tenant_id, confirmation_id, new_status)

        confirmation.status = new_status
        confirmation.decided_at = datetime.utcnow()
        return confirmation

    async def validate_for_execution(
        self,
        tenant_id: uuid.UUID,
        confirmation_id: uuid.UUID,
        tool_name: str,
        tool_payload: Dict[str, Any],
    ) -> Confirmation:
        """
        Validate that:
        1. Confirmation exists for this tenant
        2. It is APPROVED
        3. The payload hash matches (anti-replay / anti-tamper)
        """
        confirmation = await self._repo.get_by_id(tenant_id, confirmation_id)
        if confirmation is None:
            raise ConfirmationRequired(uuid.uuid4(), tool_name)

        if confirmation.status != ConfirmationStatus.APPROVED:
            raise ConfirmationDenied(confirmation_id)

        # Recompute hash and verify
        expected_hash = self.compute_payload_hash(
            confirmation.tenant_id,
            confirmation.user_id,
            confirmation.session_id,
            tool_name,
            tool_payload,
        )
        if expected_hash != confirmation.tool_payload_hash:
            raise ConfirmationHashMismatch(confirmation_id)

        return confirmation
