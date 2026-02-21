"""
JWT token creation and validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from app.config import get_settings


class JWTHandler:
    """Stateless JWT helper — encode / decode access & refresh tokens."""

    def __init__(self) -> None:
        self._settings = get_settings()

    # ── Token creation ─────────────────────────────────────

    def create_access_token(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID, extra: Optional[Dict[str, Any]] = None
    ) -> str:
        payload = {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "type": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=self._settings.jwt_access_token_expire_minutes),
        }
        if extra:
            payload.update(extra)
        return jwt.encode(payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm)

    def create_refresh_token(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
        payload = {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "type": "refresh",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=self._settings.jwt_refresh_token_expire_minutes),
        }
        return jwt.encode(payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm)

    # ── Token validation ───────────────────────────────────

    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT.  Raises jwt.ExpiredSignatureError,
        jwt.InvalidTokenError on failure.
        """
        return jwt.decode(
            token,
            self._settings.jwt_secret_key,
            algorithms=[self._settings.jwt_algorithm],
        )

    def extract_user_id(self, payload: Dict[str, Any]) -> uuid.UUID:
        return uuid.UUID(payload["sub"])

    def extract_tenant_id(self, payload: Dict[str, Any]) -> uuid.UUID:
        return uuid.UUID(payload["tenant_id"])
