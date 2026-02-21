import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.infrastructure.database.models import UserModel
from app.presentation.auth import pwd_context
from app.infrastructure.database.connection import get_async_session

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def unauth_client(db_session):
    # Override database dependency to use our in-memory test DB
    app.dependency_overrides[get_async_session] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
        # Clean up overrides after test
        app.dependency_overrides.clear()

@pytest.fixture
async def test_user(db_session):
    from tests.conftest import create_tenant_and_user
    tid, uid = await create_tenant_and_user(
        db_session, "auth-tenant", "auth@test.com"
    )
    return uid, tid

async def test_protected_route_missing_token(unauth_client):
    """Verify that accessing a protected route without a token returns 403."""
    response = await unauth_client.get("/workspace")
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authenticated"}

async def test_protected_route_invalid_token(unauth_client):
    """Verify that an invalid token returns 401."""
    response = await unauth_client.get(
        "/workspace",
        headers={"Authorization": "Bearer not-a-valid-token"}
    )
    assert response.status_code == 401
    assert "Invalid token" in response.json()["detail"]

async def test_protected_route_valid_token(jwt_handler, test_user, db_session):
    """Verify that a valid token grants access."""
    uid, tid = test_user
    token = jwt_handler.create_access_token(uid, tid)
    
    app.dependency_overrides[get_async_session] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": f"Bearer {token}"}
    ) as client:
        response = await client.get("/workspace")
        app.dependency_overrides.clear()
        
        # 200 OK means authentication succeeded
        assert response.status_code == 200
        assert "stats" in response.json()
