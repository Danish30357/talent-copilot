"""
Tool orchestrator — maps tool names to implementations and enforces confirmation gate.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from app.application.confirmation_service import ConfirmationService
from app.application.job_service import JobService
from app.domain.enums import ToolName
from app.domain.interfaces import IConfirmationRepository, IJobRepository


class ToolService:
    """
    Central orchestrator for tool execution.

    Flow:
    1. tool_decision identifies a tool request
    2. ConfirmationService creates a pending confirmation
    3. User approves → ToolService.execute_tool() validates confirmation then dispatches
    """

    def __init__(
        self,
        confirmation_repo: IConfirmationRepository,
        job_repo: IJobRepository,
    ) -> None:
        self._confirmation_service = ConfirmationService(confirmation_repo)
        self._job_service = JobService(job_repo)

    async def request_tool_confirmation(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        tool_name: ToolName,
        tool_payload: Dict[str, Any],
    ):
        """Create a pending confirmation for the requested tool."""
        return await self._confirmation_service.request_confirmation(
            tenant_id, user_id, session_id, tool_name, tool_payload
        )

    async def execute_tool_after_approval(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        confirmation_id: uuid.UUID,
        tool_name: ToolName,
        tool_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate confirmation, create a background job, and dispatch.
        Returns job info dictionary.
        """
        # Step 1: Validate confirmation — will raise if denied/mismatched/missing
        await self._confirmation_service.validate_for_execution(
            tenant_id, confirmation_id, tool_name.value, tool_payload
        )

        # Step 2: Create job record
        job = await self._job_service.create_job(
            tenant_id, user_id, session_id, tool_name
        )

        # Step 3: Dispatch to Celery (imported lazily to avoid circular imports)
        from app.infrastructure.jobs.tasks import dispatch_tool_task

        dispatch_tool_task(
            job_id=str(job.id),
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            session_id=str(session_id),
            tool_name=tool_name.value,
            tool_payload=tool_payload,
        )

        return {
            "job_id": str(job.id),
            "status": job.status.value,
            "tool_name": tool_name.value,
        }
