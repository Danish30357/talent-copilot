"""
Memory service — hybrid retrieval combining recent window, session summary,
and workspace artifacts.
"""

import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import get_settings
from app.domain.entities import Message, SessionSummary
from app.domain.enums import MessageRole
from app.domain.interfaces import (
    ICandidateRepository,
    IMessageRepository,
    IRepositoryRepo,
    ISessionSummaryRepository,
)

settings = get_settings()


class MemoryService:
    """Builds combined retrieval context for LangGraph nodes."""

    def __init__(
        self,
        message_repo: IMessageRepository,
        summary_repo: ISessionSummaryRepository,
        candidate_repo: ICandidateRepository,
        repository_repo: IRepositoryRepo,
        job_repo=None,
    ) -> None:
        self._message_repo = message_repo
        self._summary_repo = summary_repo
        self._candidate_repo = candidate_repo
        self._repository_repo = repository_repo
        self._job_repo = job_repo

    # ── Recent window ──────────────────────────────────────

    async def get_recent_messages(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> List[Message]:
        return await self._message_repo.get_recent(
            tenant_id, session_id, limit=settings.memory_window_size
        )

    # ── Session summary ────────────────────────────────────

    async def get_session_summary(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> Optional[SessionSummary]:
        return await self._summary_repo.get_latest(tenant_id, session_id)

    async def should_summarise(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> bool:
        count = await self._message_repo.count(tenant_id, session_id)
        latest_summary = await self._summary_repo.get_latest(tenant_id, session_id)
        if latest_summary is None:
            return count >= settings.summary_threshold
        return count - latest_summary.message_count_at_summary >= settings.summary_threshold

    async def save_summary(self, summary: SessionSummary) -> SessionSummary:
        return await self._summary_repo.create(summary)

    # ── Workspace artifacts ────────────────────────────────

    async def get_workspace_context(self, tenant_id: uuid.UUID, session_id: uuid.UUID = None) -> str:
        """Build a textual overview of workspace artifacts for context injection.
        Includes saved candidates, ingested repositories, AND pending parse results."""
        candidates = await self._candidate_repo.list_all(tenant_id, limit=10)
        repos = await self._repository_repo.list_all(tenant_id, limit=10)

        parts: List[str] = []
        if candidates:
            parts.append("## Candidate Profiles in Workspace")
            for c in candidates:
                skills = ", ".join(c.skills[:10]) if c.skills else "N/A"
                parts.append(f"- **{c.full_name}** ({c.email or 'no email'}) — Skills: {skills}")

        if repos:
            parts.append("\n## Ingested Repositories in Workspace")
            for r in repos:
                langs = ", ".join(r.languages[:5]) if r.languages else "N/A"
                desc = r.description[:100] if r.description else "No description"
                parts.append(f"- **{r.repo_name}** ({r.repo_url}) — Languages: {langs} — {desc}")
                if r.readme_content:
                    parts.append(f"  README excerpt: {r.readme_content[:300]}...")

        # Include pending CV parse results from completed jobs
        if self._job_repo and session_id:
            try:
                jobs = await self._job_repo.list_for_session(tenant_id, session_id)
                for job in jobs:
                    if job.tool_name.value == "cv_parsing" and job.status.value == "completed" and job.result:
                        result = job.result
                        if result.get("parsed_only"):
                            parts.append("\n## Parsed CV (Pending Save)")
                            parts.append(f"- **Name:** {result.get('full_name', 'N/A')}")
                            parts.append(f"- **Email:** {result.get('email', 'N/A')}")
                            skills = result.get("skills", [])
                            parts.append(f"- **Skills:** {', '.join(skills[:15]) if skills else 'N/A'}")
                            exp = result.get("experience", [])
                            if exp:
                                parts.append(f"- **Experience:** {len(exp)} entries")
                                for e in exp[:3]:
                                    if isinstance(e, dict):
                                        parts.append(f"  - {e.get('title', '')} at {e.get('company', '')} ({e.get('duration', '')})")
                            edu = result.get("education", [])
                            if edu:
                                parts.append(f"- **Education:** {len(edu)} entries")
                                for ed in edu[:3]:
                                    if isinstance(ed, dict):
                                        parts.append(f"  - {ed.get('degree', '')} — {ed.get('institution', '')}")
            except Exception:
                pass  # Non-critical: don't break chat if job lookup fails

        return "\n".join(parts) if parts else ""

    # ── Combined context builder ───────────────────────────

    async def build_context(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> List[Any]:
        """
        Build the full context for the LLM:
        1. System message with workspace artifacts
        2. Session summary (if available)
        3. Recent messages
        """
        lc_messages: List[Any] = []

        # System prompt with workspace context
        workspace_ctx = await self.get_workspace_context(tenant_id, session_id)
        system_text = (
            "You are TalentCopilot, an AI assistant for recruiting teams. "
            "You help with candidate evaluation, repository analysis, and hiring decisions.\n"
            "You have access to the following tools:\n"
            "- github_ingestion: Ingest and analyse a public GitHub repository\n"
            "- cv_parsing: Parse a CV/resume and extract structured profile data\n"
            "IMPORTANT: Before using any tool, you MUST ask for user confirmation.\n"
            "When the user asks about candidates, repositories, or skills, use the workspace "
            "data below to give specific, data-driven answers.\n"
        )
        if workspace_ctx:
            system_text += f"\n--- Current Workspace Data ---\n{workspace_ctx}\n"
        lc_messages.append(SystemMessage(content=system_text))

        # Session summary
        summary = await self.get_session_summary(tenant_id, session_id)
        if summary:
            lc_messages.append(
                SystemMessage(content=f"[Previous conversation summary]\n{summary.summary_text}")
            )

        # Recent messages
        recent = await self.get_recent_messages(tenant_id, session_id)
        for msg in recent:
            if msg.role == MessageRole.USER:
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                lc_messages.append(AIMessage(content=msg.content))
            elif msg.role == MessageRole.SYSTEM:
                lc_messages.append(SystemMessage(content=msg.content))

        return lc_messages
