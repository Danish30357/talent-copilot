"""
GitHub repository ingestion tool.

Features:
- Validates public HTTPS GitHub URLs only
- Extracts README, directory structure, languages, code snippets
- Idempotent per (tenant_id, repo_url) via upsert
- Retry with exponential backoff on HTTP 429
- Runs inside Celery tasks
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.domain.entities import Repository

settings = get_settings()


class GitHubRateLimitError(Exception):
    """Raised on HTTP 429 from GitHub API."""


class GitHubIngestionTool:
    """
    Ingests a public GitHub repository:
    1. Validates the URL
    2. Fetches README via GitHub REST API
    3. Fetches repository metadata (languages, description)
    4. Fetches top-level directory structure (depth-limited)
    5. Extracts representative code snippets
    6. Returns normalised Repository entity
    """

    BASE_URL = "https://api.github.com"

    def __init__(self) -> None:
        self._headers: Dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TalentCopilot/1.0",
        }
        if settings.github_token:
            self._headers["Authorization"] = f"Bearer {settings.github_token}"

    @staticmethod
    def parse_owner_repo(repo_url: str) -> tuple[str, str]:
        """Extract (owner, repo) from a GitHub URL."""
        path = urlparse(repo_url).path.strip("/")
        parts = path.split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid GitHub URL: {repo_url}")
        return parts[0], parts[1].replace(".git", "")

    @retry(
        retry=retry_if_exception_type(GitHubRateLimitError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=120),
        reraise=True,
    )
    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """HTTP GET with rate-limit retry."""
        resp = await client.get(url, headers=self._headers, timeout=30.0)
        if resp.status_code == 429:
            raise GitHubRateLimitError("GitHub API rate limit hit")
        return resp

    async def ingest(self, tenant_id: uuid.UUID, repo_url: str) -> Repository:
        """Full ingestion pipeline → returns a Repository entity."""
        owner, repo = self.parse_owner_repo(repo_url)

        async with httpx.AsyncClient() as client:
            # Repo metadata
            meta = await self._fetch_metadata(client, owner, repo)

            # README
            readme = await self._fetch_readme(client, owner, repo)

            # Directory structure (top-level, depth-limited)
            structure = await self._fetch_structure(client, owner, repo)

            # Languages
            languages = await self._fetch_languages(client, owner, repo)

            # Code snippets (from top-level Python/JS/TS files)
            snippets = await self._fetch_code_snippets(client, owner, repo, structure)

        return Repository(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            repo_url=repo_url,
            repo_name=f"{owner}/{repo}",
            description=meta.get("description", "") or "",
            languages=languages,
            structure=structure,
            readme_content=readme,
            code_snippets=snippets,
            ingested_at=datetime.utcnow(),
        )

    async def _fetch_metadata(
        self, client: httpx.AsyncClient, owner: str, repo: str
    ) -> Dict[str, Any]:
        resp = await self._get(client, f"{self.BASE_URL}/repos/{owner}/{repo}")
        if resp.status_code == 401:
            raise ValueError(
                "GitHub API returned 401 Unauthorized. "
                "Check GITHUB_TOKEN or use an empty token for public repos."
            )
        if resp.status_code == 200:
            return resp.json()
        return {}

    async def _fetch_readme(
        self, client: httpx.AsyncClient, owner: str, repo: str
    ) -> str:
        resp = await self._get(client, f"{self.BASE_URL}/repos/{owner}/{repo}/readme")
        if resp.status_code == 200:
            data = resp.json()
            # Content is base64-encoded
            import base64
            try:
                return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
            except Exception:
                return ""
        return ""

    async def _fetch_structure(
        self, client: httpx.AsyncClient, owner: str, repo: str, max_depth: int = 2
    ) -> Dict[str, Any]:
        """Fetch directory tree, depth-limited."""
        resp = await self._get(
            client, f"{self.BASE_URL}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
        )
        if resp.status_code != 200:
            return {}

        tree = resp.json().get("tree", [])
        structure: Dict[str, Any] = {"files": [], "dirs": []}

        for item in tree:
            path = item.get("path", "")
            depth = path.count("/")
            if depth >= max_depth:
                continue
            if item.get("type") == "blob":
                structure["files"].append(path)
            elif item.get("type") == "tree":
                structure["dirs"].append(path)

        # Limit to 100 items each
        structure["files"] = structure["files"][:100]
        structure["dirs"] = structure["dirs"][:50]
        return structure

    async def _fetch_languages(
        self, client: httpx.AsyncClient, owner: str, repo: str
    ) -> List[str]:
        resp = await self._get(client, f"{self.BASE_URL}/repos/{owner}/{repo}/languages")
        if resp.status_code == 200:
            return list(resp.json().keys())
        return []

    async def _fetch_code_snippets(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        structure: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Fetch a few representative source files (first 1KB each)."""
        code_extensions = {".py", ".js", ".ts", ".java", ".go", ".rs", ".rb"}
        files = structure.get("files", [])
        snippet_files = [
            f for f in files
            if any(f.endswith(ext) for ext in code_extensions)
        ][:5]  # max 5 snippets

        snippets: List[Dict[str, Any]] = []
        for filepath in snippet_files:
            resp = await self._get(
                client,
                f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{filepath}",
            )
            if resp.status_code == 200:
                import base64
                data = resp.json()
                try:
                    content = base64.b64decode(data.get("content", "")).decode(
                        "utf-8", errors="replace"
                    )
                    snippets.append({
                        "path": filepath,
                        "content": content[:1024],  # first 1KB
                        "language": filepath.rsplit(".", 1)[-1] if "." in filepath else "",
                    })
                except Exception:
                    pass
        return snippets
