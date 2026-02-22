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
                parts.append(f"- **{r.repo_name}** ({r.repo_url}) — Languages: {langs}")
                parts.append(f"  *Description:* {desc}")
                
                # Include File Structure summary
                structure = r.structure or {}
                files = structure.get("files", [])
                dirs = structure.get("dirs", [])
                if files or dirs:
                    parts.append(f"  *Key Directories:* {', '.join(dirs[:10]) if dirs else 'root only'}")
                    parts.append(f"  *Sample Files:* {', '.join(files[:15])}")
                
                if r.readme_content:
                    parts.append(f"  *README excerpt:* {r.readme_content[:400].strip()}...")
                
                # Include actual code snippet content for deeper understanding
                if r.code_snippets:
                    parts.append(f"  *Code Snippets Analyzed ({len(r.code_snippets)} files):*")
                    for snippet in r.code_snippets[:3]:
                        path = snippet.get("path", "")
                        content = snippet.get("content", "")[:500].strip()
                        if content:
                            parts.append(f"    [{path}]:\n    ```\n    {content}\n    ```")

                # Extract quality signals heuristically from the file tree
                all_files_lower = [f.lower() for f in files]
                all_dirs_lower = [d.lower() for d in dirs]
                signals = []
                has_tests = any("test" in f or "spec" in f for f in all_files_lower) or \
                            any("test" in d for d in all_dirs_lower)
                has_ci = any(".github" in d or "ci" in d for d in all_dirs_lower) or \
                          any("workflow" in f or ".travis" in f or "jenkins" in f for f in all_files_lower)
                has_docker = any("dockerfile" in f for f in all_files_lower)
                has_deps = any(f in all_files_lower for f in ["requirements.txt", "pyproject.toml", "package.json", "go.mod", "pom.xml"])
                has_lint = any(f in all_files_lower for f in [".flake8", ".eslintrc", "pylintrc", ".pre-commit-config.yaml", "mypy.ini"])
                has_docs = any("readme" in f or "docs" in d for f in all_files_lower for d in all_dirs_lower)
                signals.append(f"Tests: {'✅ Yes' if has_tests else '❌ Not found'}")
                signals.append(f"CI/CD: {'✅ Yes' if has_ci else '❌ Not found'}")
                signals.append(f"Docker: {'✅ Yes' if has_docker else '❌ Not found'}")
                signals.append(f"Dependency Management: {'✅ Yes' if has_deps else '❌ Not found'}")
                signals.append(f"Linting/Code Quality Config: {'✅ Yes' if has_lint else '❌ Not found'}")
                signals.append(f"Documentation: {'✅ Yes' if has_docs else '❌ Not found'}")
                parts.append(f"  *Quality Signals:* {' | '.join(signals)}")

        # Include active jobs and pending CV parse results
        if self._job_repo and session_id:
            try:
                jobs = await self._job_repo.list_for_session(tenant_id, session_id)
                active_jobs = [j for j in jobs if j.status.value in ("queued", "running")]
                if active_jobs:
                    parts.append("\n## Active Jobs (In Progress)")
                    for j in active_jobs:
                        parts.append(f"- **{j.tool_name.value}** — Status: {j.status.value}")

                for job in jobs:
                    if job.tool_name.value == "cv_parsing" and job.status.value == "completed" and job.result:
                        result = job.result
                        # ... (existing CV parsing logic)
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
            "You are TalentCopilot, an AI assistant for recruiting teams. Be professional, specific, and data-driven.\n\n"
            "## YOUR CAPABILITIES\n"
            "You help recruiters with these tasks — always use the Workspace Data below to give specific answers:\n"
            "1. **Repository Analysis** — Describe structure, tech stack, code quality signals, and architecture patterns\n"
            "2. **Candidate Evaluation** — Summarise skills, experience, and suitability for specific roles\n"
            "3. **Candidate vs Repo Matching** — Compare candidate skills against a repo's tech stack. Say explicitly: strong match / partial match / gap\n"
            "4. **Interview Question Generation** — Generate tailored technical interview questions based on the repo's stack or candidate's background\n"
            "5. **Evaluation Notes** — Write structured evaluation notes for a candidate relevant to a role or repo\n\n"
            "## YOUR TOOLS\n"
            "- **github_ingestion**: Fetches and indexes a GitHub repo — use when user shares a new URL\n"
            "- **cv_parsing**: Parses a CV file — use when user uploads a resume\n\n"
            "## TOOL INVOCATION (STRICT FORMAT)\n"
            "[TOOL_REQUEST]{\"tool\": \"github_ingestion\", \"payload\": {\"repo_url\": \"<URL>\"}}[/TOOL_REQUEST]\n"
            "Example: [TOOL_REQUEST]{\"tool\": \"github_ingestion\", \"payload\": {\"repo_url\": \"https://github.com/user/repo\"}}[/TOOL_REQUEST]\n\n"
            "## RULES\n"
            "1. GitHub URL given → check workspace below. If NEW → announce + include [TOOL_REQUEST] tag. If already ingested → answer from data.\n"
            "2. Never say 'I will analyze' without including the [TOOL_REQUEST] tag in the same message.\n"
            "3. When asked about quality signals, ALWAYS reference the Quality Signals section in workspace data.\n"
            "4. When asked to compare a candidate to a repo, list matching skills, missing skills, and give an overall verdict.\n"
            "5. When generating interview questions, make them specific to the actual tech stack found in the repo.\n\n"
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
