"""
Chat service — orchestrates the full conversational flow through LangGraph.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from app.application.memory_service import MemoryService
from app.domain.entities import Message, Session, SessionSummary
from app.domain.enums import MessageRole
from app.domain.interfaces import (
    ICandidateRepository,
    IConfirmationRepository,
    IJobRepository,
    IMessageRepository,
    IRepositoryRepo,
    ISessionRepository,
    ISessionSummaryRepository,
)


class ChatService:
    """High-level orchestrator: receive user message → build context → run graph → persist."""

    def __init__(
        self,
        session_repo: ISessionRepository,
        message_repo: IMessageRepository,
        summary_repo: ISessionSummaryRepository,
        confirmation_repo: IConfirmationRepository,
        job_repo: IJobRepository,
        candidate_repo: ICandidateRepository,
        repository_repo: IRepositoryRepo,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._memory = MemoryService(message_repo, summary_repo, candidate_repo, repository_repo, job_repo=job_repo)
        self._confirmation_repo = confirmation_repo
        self._job_repo = job_repo

    # ── Main entry point ───────────────────────────────────

    async def handle_message(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: Optional[uuid.UUID],
        content: str,
    ) -> Dict[str, Any]:
        """
        Full chat cycle:
        1. Ensure session exists
        2. Persist user message
        3. Build memory context
        4. Run LangGraph
        5. Persist assistant reply
        6. Trigger summarisation if needed
        7. Return response (possibly with confirmation request)
        """
        # 1. Session
        if session_id is None:
            session = Session(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                title=content[:80],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            await self._session_repo.create(session)
            session_id = session.id
        else:
            existing = await self._session_repo.get_by_id(tenant_id, session_id)
            if existing is None:
                session = Session(
                    id=session_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    title=content[:80],
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                await self._session_repo.create(session)

        # 2. Persist user message
        user_msg = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            role=MessageRole.USER,
            content=content,
            created_at=datetime.utcnow(),
        )
        await self._message_repo.create(user_msg)

        # 3. Build context
        context_messages = await self._memory.build_context(tenant_id, session_id)

        # 4. Run LangGraph
        from app.infrastructure.graph.builder import build_graph

        graph = build_graph(self._confirmation_repo, self._job_repo)
        graph_input = {
            "messages": context_messages,
            "current_state": "conversation",
            "tool_request": None,
            "confirmation_id": None,
            "tool_result": None,
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "session_id": str(session_id),
        }

        result = await graph.ainvoke(graph_input)

        # 5. Extract response
        response_content = result.get("response_text", "I'm sorry, I couldn't process that.")
        confirmation_required = result.get("confirmation_required", False)
        confirmation_id = result.get("confirmation_id")
        confirmation_details = result.get("confirmation_details")

        # 6. Persist assistant reply
        assistant_msg = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=response_content,
            metadata={
                "confirmation_required": confirmation_required,
                "confirmation_id": str(confirmation_id) if confirmation_id else None,
            },
            created_at=datetime.utcnow(),
        )
        await self._message_repo.create(assistant_msg)

        # 7. Check if summarisation is needed
        if await self._memory.should_summarise(tenant_id, session_id):
            await self._trigger_summarisation(tenant_id, session_id)

        return {
            "session_id": str(session_id),
            "message": {
                "id": str(assistant_msg.id),
                "role": assistant_msg.role.value,
                "content": assistant_msg.content,
                "metadata": assistant_msg.metadata,
                "created_at": assistant_msg.created_at.isoformat(),
            },
            "confirmation_required": confirmation_required,
            "confirmation_id": str(confirmation_id) if confirmation_id else None,
            "confirmation_details": confirmation_details,
        }

    # ── Summarisation ──────────────────────────────────────

    async def _trigger_summarisation(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> None:
        """Generate and persist a session summary using the LLM."""
        from app.infrastructure.llm.langchain_provider import get_llm

        messages = await self._message_repo.get_recent(tenant_id, session_id, limit=100)
        if not messages:
            return

        conversation_text = "\n".join(
            f"{msg.role.value}: {msg.content}" for msg in messages
        )

        llm = get_llm()
        prompt = (
            "Summarise the following conversation concisely, capturing key topics, "
            "decisions, tool results, and any outstanding actions:\n\n"
            f"{conversation_text}\n\nSummary:"
        )
        response = await llm.ainvoke(prompt)
        summary_text = response.content if hasattr(response, "content") else str(response)

        count = await self._message_repo.count(tenant_id, session_id)
        summary = SessionSummary(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            summary_text=summary_text,
            message_count_at_summary=count,
            created_at=datetime.utcnow(),
        )
        await self._memory.save_summary(summary)

    # ── History ────────────────────────────────────────────

    async def get_history(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ):
        return await self._message_repo.get_range(tenant_id, session_id, offset, limit)

    async def list_sessions(self, tenant_id: uuid.UUID, user_id: uuid.UUID):
        return await self._session_repo.list_for_user(tenant_id, user_id)
