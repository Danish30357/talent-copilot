"""
FastAPI dependency that extracts and validates JWT from the Authorization header,
returning a CurrentUser DTO with tenant_id and user_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infrastructure.security.jwt_handler import JWTHandler

_bearer_scheme = HTTPBearer()


@dataclass(frozen=True)
class CurrentUser:
    """Immutable identity extracted from a validated token."""
    user_id: uuid.UUID
    tenant_id: uuid.UUID


def get_jwt_handler() -> JWTHandler:
    return JWTHandler()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
) -> CurrentUser:
    """
    Dependency: validates Bearer token and returns CurrentUser.
    Raises 401 on invalid or expired token.
    """
    token = credentials.credentials
    try:
        payload = jwt_handler.decode_token(token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — access token required",
        )

    return CurrentUser(
        user_id=jwt_handler.extract_user_id(payload),
        tenant_id=jwt_handler.extract_tenant_id(payload),
    )
