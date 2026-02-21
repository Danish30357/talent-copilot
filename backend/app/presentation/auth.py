"""
Authentication routes — login and token refresh.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_user_repo
from app.dto.requests import LoginRequest, RefreshTokenRequest
from app.dto.responses import TokenResponse
from app.infrastructure.database.connection import get_async_session
from app.infrastructure.database.models import TenantModel
from app.infrastructure.database.repositories import UserRepository
from app.infrastructure.security.jwt_handler import JWTHandler
from app.infrastructure.security.rate_limiter import limiter

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Authenticate user and return JWT tokens."""
    from sqlalchemy import select, and_

    # Look up tenant
    stmt = select(TenantModel).where(TenantModel.name == body.tenant_name)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant or credentials",
        )

    # Look up user
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(tenant.id, body.email)

    if user is None or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant or credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    jwt_handler = JWTHandler()
    return TokenResponse(
        access_token=jwt_handler.create_access_token(user.id, tenant.id),
        refresh_token=jwt_handler.create_refresh_token(user.id, tenant.id),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("5/minute")
async def refresh_token(
    request: Request,
    body: RefreshTokenRequest,
) -> TokenResponse:
    """Generate new access token from refresh token."""
    jwt_handler = JWTHandler()
    try:
        payload = jwt_handler.decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token",
        )

    user_id = jwt_handler.extract_user_id(payload)
    tenant_id = jwt_handler.extract_tenant_id(payload)

    return TokenResponse(
        access_token=jwt_handler.create_access_token(user_id, tenant_id),
        refresh_token=jwt_handler.create_refresh_token(user_id, tenant_id),
    )
