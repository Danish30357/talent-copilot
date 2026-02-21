"""
Seed script to create a default tenant and user for testing.
"""

import asyncio
import uuid
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.config import get_settings
from app.infrastructure.database.models import TenantModel, UserModel

async def seed_data():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=True)
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash("password123")
    
    tenant_name = "acme-corp"
    email = "recruiter@acme.com"

    async with async_session() as session:
        # Check if tenant exists
        from sqlalchemy import select
        stmt = select(TenantModel).where(TenantModel.name == tenant_name)
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            tenant = TenantModel(
                id=str(uuid.uuid4()),
                name=tenant_name
            )
            session.add(tenant)
            await session.commit()
            print(f"Created tenant: {tenant_name} ({tenant.id})")
        else:
            print(f"Tenant {tenant_name} already exists.")
            
        # Check if user exists
        stmt = select(UserModel).where(UserModel.email == email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            user = UserModel(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                email=email,
                hashed_password=hashed_password,
                full_name="Acme Recruiter",
                is_active=True
            )
            session.add(user)
            await session.commit()
            print(f"Created user: {email} ({user.id})")
        else:
            user.hashed_password = hashed_password
            session.add(user)
            await session.commit()
            print(f"User {email} already exists. Reset password.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed_data())
