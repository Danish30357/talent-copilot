"""
Workspace routes — candidates, repositories, CV upload, GitHub ingestion,
combined workspace snapshot.
"""

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.application.confirmation_service import ConfirmationService
from app.application.job_service import JobService
from app.config import get_settings
from app.dependencies import (
    get_candidate_repo,
    get_confirmation_repo,
    get_job_repo,
    get_repository_repo,
    get_session_repo,
    get_summary_repo,
)
from app.domain.enums import ToolName
from app.domain.exceptions import FileValidationError
from app.dto.requests import GitHubIngestRequest
from app.dto.responses import CandidateResponse, ConfirmationResponse, JobStatusResponse, RepositoryResponse
from app.infrastructure.database.repositories import (
    CandidateRepository,
    ConfirmationRepository,
    JobRepository,
    RepositoryRepo,
    SessionRepository,
    SessionSummaryRepository,
)
from app.infrastructure.security.auth_middleware import CurrentUser, get_current_user
from app.infrastructure.security.rate_limiter import limiter

router = APIRouter()
settings = get_settings()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def _validate_file(file: UploadFile) -> None:
    """Validate file extension and size."""
    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in settings.allowed_extensions_list:
        raise FileValidationError(
            f"File type '.{ext}' not allowed. Allowed: {settings.allowed_extensions}"
        )


# ─────────────────────────────────────────────────────────────
# GET /workspace — Combined workspace snapshot
# ─────────────────────────────────────────────────────────────

@router.get("/workspace")
@limiter.limit("30/minute")
async def get_workspace_snapshot(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    candidate_repo: CandidateRepository = Depends(get_candidate_repo),
    repository_repo: RepositoryRepo = Depends(get_repository_repo),
    session_repo: SessionRepository = Depends(get_session_repo),
    summary_repo: SessionSummaryRepository = Depends(get_summary_repo),
) -> Dict[str, Any]:
    """
    Full workspace snapshot for the current tenant/user.
    Returns candidates, repositories, sessions, and latest summaries.
    """
    candidates = await candidate_repo.list_all(user.tenant_id, limit=50)
    repos = await repository_repo.list_all(user.tenant_id, limit=50)
    sessions = await session_repo.list_for_user(user.tenant_id, user.user_id, limit=20)

    # Get latest summary for each session
    session_data = []
    for s in sessions:
        summary = await summary_repo.get_latest(user.tenant_id, s.id)
        session_data.append({
            "id": str(s.id),
            "title": s.title,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "latest_summary": summary.summary_text if summary else None,
        })

    return {
        "tenant_id": str(user.tenant_id),
        "candidates": [
            {
                "id": str(c.id),
                "full_name": c.full_name,
                "email": c.email,
                "phone": c.phone,
                "skills": c.skills,
                "experience": c.experience,
                "education": c.education,
                "projects": c.projects,
                "source_filename": c.source_filename,
                "created_at": c.created_at.isoformat(),
            }
            for c in candidates
        ],
        "repositories": [
            {
                "id": str(r.id),
                "repo_url": r.repo_url,
                "repo_name": r.repo_name,
                "description": r.description,
                "languages": r.languages,
                "ingested_at": r.ingested_at.isoformat(),
            }
            for r in repos
        ],
        "sessions": session_data,
        "stats": {
            "total_candidates": len(candidates),
            "total_repos": len(repos),
            "total_sessions": len(sessions),
        },
    }


# ─────────────────────────────────────────────────────────────
# Candidate CRUD
# ─────────────────────────────────────────────────────────────

@router.get("/workspace/candidates", response_model=List[CandidateResponse])
@limiter.limit("30/minute")
async def list_candidates(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    candidate_repo: CandidateRepository = Depends(get_candidate_repo),
) -> List[CandidateResponse]:
    """List all parsed and saved candidate profiles for the tenant."""
    candidates = await candidate_repo.list_all(user.tenant_id, limit=min(limit, 100), offset=offset)
    return [
        CandidateResponse(
            id=c.id, full_name=c.full_name, email=c.email, phone=c.phone,
            skills=c.skills, experience=c.experience, education=c.education,
            projects=c.projects, source_filename=c.source_filename,
            created_at=c.created_at,
        )
        for c in candidates
    ]


# ─────────────────────────────────────────────────────────────
# Repository CRUD
# ─────────────────────────────────────────────────────────────

@router.get("/workspace/repositories", response_model=List[RepositoryResponse])
@limiter.limit("30/minute")
async def list_repositories(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    repository_repo: RepositoryRepo = Depends(get_repository_repo),
) -> List[RepositoryResponse]:
    """List all ingested GitHub repositories for the tenant."""
    repos = await repository_repo.list_all(user.tenant_id, limit=min(limit, 100), offset=offset)
    return [
        RepositoryResponse(
            id=r.id, repo_url=r.repo_url, repo_name=r.repo_name,
            description=r.description, languages=r.languages,
            ingested_at=r.ingested_at,
        )
        for r in repos
    ]


# ─────────────────────────────────────────────────────────────
# CV Upload — HITL Step 1: Parse
# ─────────────────────────────────────────────────────────────

@router.post("/upload/cv")
@limiter.limit("5/minute")
async def upload_cv(
    request: Request,
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    confirmation_repo: ConfirmationRepository = Depends(get_confirmation_repo),
) -> dict:
    """
    Upload a CV/resume file and request HITL confirmation before parsing.
    """
    # Validate file type
    try:
        _validate_file(file)
    except FileValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check file size
    contents = await file.read()
    if len(contents) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb}MB",
        )

    # Save file temporarily
    file_id = uuid.uuid4()
    file_ext = Path(file.filename or "upload").suffix
    saved_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    with open(saved_path, "wb") as f:
        f.write(contents)

    # Create HITL confirmation for parsing
    confirmation_service = ConfirmationService(confirmation_repo)
    confirmation = await confirmation_service.request_confirmation(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=session_id,
        tool_name=ToolName.CV_PARSING,
        tool_payload={
            "file_path": str(saved_path),
            "filename": file.filename or "unknown",
        },
    )

    return {
        "message": (
            f"CV uploaded. "
            f"Would you like me to parse this CV: '{file.filename}'? "
            f"Please confirm to proceed. (yes/no)"
        ),
        "confirmation_id": str(confirmation.id),
        "filename": file.filename,
        "file_size_bytes": len(contents),
        "hitl_step": "parsing",
    }


# ─────────────────────────────────────────────────────────────
# CV Save Confirmation — HITL Step 2 (triggered programmatically
# ─────────────────────────────────────────────────────────────

@router.post("/upload/cv/save-confirmation")
@limiter.limit("10/minute")
async def request_cv_save(
    request: Request,
    session_id: uuid.UUID,
    parse_job_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    confirmation_repo: ConfirmationRepository = Depends(get_confirmation_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> dict:
    """
    Create a cv_save confirmation after a cv_parsing job completes.
    """
    # Load parse job to get candidate name
    job_service = JobService(job_repo)
    try:
        parse_job = await job_service.get_status(user.tenant_id, parse_job_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Parse job not found")

    if parse_job.status.value != "completed":
        raise HTTPException(
            status_code=400,
            detail="Parsing is not yet complete. Poll the job status first.",
        )
    if not parse_job.result:
        raise HTTPException(status_code=400, detail="No parsed data found in job result")

    candidate_name = parse_job.result.get("full_name", "Unknown")

    # Create HITL confirmation for saving
    confirmation_service = ConfirmationService(confirmation_repo)
    confirmation = await confirmation_service.request_confirmation(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=session_id,
        tool_name=ToolName.CV_SAVE,
        tool_payload={"parse_job_id": str(parse_job_id)},
    )

    return {
        "message": (
            f"Do you want me to save this candidate profile to the workspace? "
            f"Candidate: {candidate_name}"
        ),
        "confirmation_id": str(confirmation.id),
        "candidate_preview": {
            "full_name": parse_job.result.get("full_name"),
            "email": parse_job.result.get("email"),
            "skills": parse_job.result.get("skills", [])[:10],
            "experience_count": len(parse_job.result.get("experience", [])),
            "education_count": len(parse_job.result.get("education", [])),
        },
        "hitl_step": "saving",
        "parse_job_id": str(parse_job_id),
    }


# ─────────────────────────────────────────────────────────────
# GitHub Ingestion — HITL: Request confirmation
# ─────────────────────────────────────────────────────────────

@router.post("/ingest/github")
@limiter.limit("5/minute")
async def request_github_ingestion(
    request: Request,
    body: GitHubIngestRequest,
    session_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    confirmation_repo: ConfirmationRepository = Depends(get_confirmation_repo),
) -> dict:
    """
    Request GitHub repository ingestion — creates a HITL confirmation that
    must be approved before the ingestion job starts.

    Asks: "Would you like me to crawl this repository: <repo_url>?"
    """
    confirmation_service = ConfirmationService(confirmation_repo)
    confirmation = await confirmation_service.request_confirmation(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=session_id,
        tool_name=ToolName.GITHUB_INGESTION,
        tool_payload={"repo_url": body.repo_url},
    )

    return {
        "message": (
            f"Would you like me to crawl this repository: {body.repo_url} ? (yes/no)"
        ),
        "confirmation_id": str(confirmation.id),
        "repo_url": body.repo_url,
    }
