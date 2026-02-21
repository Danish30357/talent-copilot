"""
Celery tasks for background tool execution.

Each task:
1. Updates job status to RUNNING
2. Executes the tool
3. Persists results to DB (only when explicitly approved)
4. Updates job status to COMPLETED or FAILED

CV HITL Flow (two-step):
  Step 1 — cv_parsing job: parse file → store structured data in job result (NO persist)
  Step 2 — cv_save job:    user approves → persist Candidate from job result
"""

import asyncio
import logging
import os
import uuid
from typing import Any, Dict

from app.infrastructure.jobs.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async code inside a sync Celery task.
    Creates a fresh event loop each time to avoid stale-loop errors in forked workers.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def dispatch_tool_task(
    job_id: str,
    tenant_id: str,
    user_id: str,
    session_id: str,
    tool_name: str,
    tool_payload: Dict[str, Any],
) -> None:
    """Dispatch the appropriate Celery task based on tool_name."""
    if tool_name == "github_ingestion":
        ingest_github_repo.delay(
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            repo_url=tool_payload.get("repo_url", ""),
        )
    elif tool_name == "cv_parsing":
        parse_cv_file.delay(
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            file_path=tool_payload.get("file_path", ""),
            filename=tool_payload.get("filename", ""),
        )
    elif tool_name == "cv_save":
        save_candidate_profile.delay(
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            parse_job_id=tool_payload.get("parse_job_id", ""),
        )
    else:
        logger.error(f"Unknown tool: {tool_name}")


# ─────────────────────────────────────────────────────────────
# Task 1: GitHub Repository Ingestion
# ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True, max_retries=3, default_retry_delay=60, acks_late=True,
    name="app.infrastructure.jobs.tasks.ingest_github_repo",
)
def ingest_github_repo(self, job_id, tenant_id, user_id, session_id, repo_url):
    logger.info(f"[Job {job_id}] Starting GitHub ingestion for {repo_url}")

    async def _run():
        from app.infrastructure.database.connection import create_task_session_factory
        from app.infrastructure.database.repositories import JobRepository, RepositoryRepo
        from app.infrastructure.tools.github_ingestion import GitHubIngestionTool
        from app.domain.enums import JobStatus

        sf = create_task_session_factory()
        tid = uuid.UUID(tenant_id)

        async with sf() as session:
            job_repo = JobRepository(session)
            repo_repo = RepositoryRepo(session)
            await job_repo.update_status(tid, uuid.UUID(job_id), JobStatus.RUNNING)
            await session.commit()

            try:
                tool = GitHubIngestionTool()
                repo_entity = await tool.ingest(tid, repo_url)
                await repo_repo.upsert(repo_entity)
                result = {
                    "repo_name": repo_entity.repo_name,
                    "languages": repo_entity.languages,
                    "files_count": len(repo_entity.structure.get("files", [])),
                    "description": repo_entity.description,
                }
                await job_repo.update_status(tid, uuid.UUID(job_id), JobStatus.COMPLETED, result=result)
                await session.commit()
                logger.info(f"[Job {job_id}] GitHub ingestion completed for {repo_url}")
                return {"status": "completed", "repo_name": repo_entity.repo_name}
            except Exception as e:
                logger.error(f"[Job {job_id}] GitHub ingestion failed: {e}")
                await session.rollback()
                async with sf() as es:
                    JobRepository(es)
                    await JobRepository(es).update_status(tid, uuid.UUID(job_id), JobStatus.FAILED, error_message=str(e))
                    await es.commit()
                raise

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error(f"[Job {job_id}] Retrying due to: {exc}")
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
# Task 2: CV Parsing — PARSE ONLY, no persistence
# ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=30, acks_late=True,
    name="app.infrastructure.jobs.tasks.parse_cv_file",
)
def parse_cv_file(self, job_id, tenant_id, user_id, session_id, file_path, filename):
    logger.info(f"[Job {job_id}] Starting CV parsing for {filename}")

    async def _run():
        from app.infrastructure.database.connection import create_task_session_factory
        from app.infrastructure.database.repositories import JobRepository
        from app.infrastructure.tools.cv_parser import CVParserTool
        from app.domain.enums import JobStatus

        sf = create_task_session_factory()
        tid = uuid.UUID(tenant_id)

        async with sf() as session:
            job_repo = JobRepository(session)
            await job_repo.update_status(tid, uuid.UUID(job_id), JobStatus.RUNNING)
            await session.commit()

            try:
                tool = CVParserTool()
                candidate = await tool.parse(tid, file_path, filename)

                parsed_result = {
                    "parse_job_id": job_id,
                    "full_name": candidate.full_name,
                    "email": candidate.email,
                    "phone": candidate.phone,
                    "skills": candidate.skills,
                    "experience": candidate.experience,
                    "education": candidate.education,
                    "projects": candidate.projects,
                    "raw_text": candidate.raw_text[:2000],
                    "source_filename": candidate.source_filename,
                    "parsed_only": True,
                }

                await job_repo.update_status(tid, uuid.UUID(job_id), JobStatus.COMPLETED, result=parsed_result)
                await session.commit()

                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"[Job {job_id}] Cleaned up temp file: {file_path}")
                except OSError as cleanup_err:
                    logger.warning(f"[Job {job_id}] Could not delete temp file: {cleanup_err}")

                logger.info(f"[Job {job_id}] CV parsing completed for {filename} (not yet saved)")
                return {"status": "completed", "candidate_name": candidate.full_name, "saved": False}

            except Exception as e:
                logger.error(f"[Job {job_id}] CV parsing failed: {e}")
                await session.rollback()
                async with sf() as es:
                    await JobRepository(es).update_status(tid, uuid.UUID(job_id), JobStatus.FAILED, error_message=str(e))
                    await es.commit()
                raise

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error(f"[Job {job_id}] Retrying due to: {exc}")
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
# Task 3: CV Save — persist after HITL approval
# ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=30, acks_late=True,
    name="app.infrastructure.jobs.tasks.save_candidate_profile",
)
def save_candidate_profile(self, job_id, tenant_id, user_id, session_id, parse_job_id):
    logger.info(f"[Job {job_id}] Saving candidate from parse job {parse_job_id}")

    async def _run():
        from app.infrastructure.database.connection import create_task_session_factory
        from app.infrastructure.database.repositories import JobRepository, CandidateRepository
        from app.domain.entities import Candidate
        from app.domain.enums import JobStatus
        from datetime import datetime

        sf = create_task_session_factory()
        tid = uuid.UUID(tenant_id)

        async with sf() as session:
            job_repo = JobRepository(session)
            candidate_repo = CandidateRepository(session)
            await job_repo.update_status(tid, uuid.UUID(job_id), JobStatus.RUNNING)
            await session.commit()

            try:
                parse_job = await job_repo.get_by_id(tid, uuid.UUID(parse_job_id))
                if parse_job is None or parse_job.result is None:
                    raise ValueError(f"Parse job {parse_job_id} not found or has no result")

                parsed = parse_job.result
                candidate = Candidate(
                    id=uuid.uuid4(), tenant_id=tid,
                    full_name=parsed.get("full_name", "Unknown"),
                    email=parsed.get("email"), phone=parsed.get("phone"),
                    skills=parsed.get("skills", []),
                    experience=parsed.get("experience", []),
                    education=parsed.get("education", []),
                    projects=parsed.get("projects", []),
                    raw_text=parsed.get("raw_text", ""),
                    source_filename=parsed.get("source_filename", ""),
                    created_at=datetime.utcnow(),
                )
                await candidate_repo.create(candidate)
                await job_repo.update_status(
                    tid, uuid.UUID(job_id), JobStatus.COMPLETED,
                    result={"candidate_id": str(candidate.id), "full_name": candidate.full_name,
                            "email": candidate.email, "skills_count": len(candidate.skills), "saved": True},
                )
                await session.commit()
                logger.info(f"[Job {job_id}] Candidate '{candidate.full_name}' saved successfully")
                return {"status": "completed", "candidate_name": candidate.full_name, "saved": True}

            except Exception as e:
                logger.error(f"[Job {job_id}] Candidate save failed: {e}")
                await session.rollback()
                async with sf() as es:
                    await JobRepository(es).update_status(tid, uuid.UUID(job_id), JobStatus.FAILED, error_message=str(e))
                    await es.commit()
                raise

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error(f"[Job {job_id}] Retrying due to: {exc}")
        raise self.retry(exc=exc)
