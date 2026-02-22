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
from sqlalchemy import select

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
        # -- TENANT A --
        tenant_name = "acme-corp"
        email = "recruiter@acme.com"
        
        # Check if tenant A exists
        # ... your code ...
        stmt = select(TenantModel).where(TenantModel.name == tenant_name)
        result = await session.execute(stmt)
        tenant_a = result.scalar_one_or_none()
        
        if not tenant_a:
            tenant_a = TenantModel(id=str(uuid.uuid4()), name=tenant_name)
            session.add(tenant_a)
            await session.commit()
            print(f"Created tenant: {tenant_name}")
            
        # Check if user A exists
        stmt = select(UserModel).where(UserModel.email == email)
        result = await session.execute(stmt)
        user_a = result.scalar_one_or_none()
        
        if not user_a:
            user_a = UserModel(
                id=str(uuid.uuid4()), tenant_id=tenant_a.id,
                email=email, hashed_password=hashed_password,
                full_name="Acme Recruiter", is_active=True
            )
            session.add(user_a)
            await session.commit()
            print(f"Created user: {email}")
            
        # -- TENANT B --
        tenant_b_name = "other-corp"
        email_b = "other@techcorp.com"
        
        stmt = select(TenantModel).where(TenantModel.name == tenant_b_name)
        result = await session.execute(stmt)
        tenant_b = result.scalar_one_or_none()
        if not tenant_b:
            tenant_b = TenantModel(id=str(uuid.uuid4()), name=tenant_b_name)
            session.add(tenant_b)
            await session.commit()
            print(f"Created tenant: {tenant_b_name}")
            
        stmt = select(UserModel).where(UserModel.email == email_b)
        result = await session.execute(stmt)
        user_b = result.scalar_one_or_none()
        if not user_b:
            user_b = UserModel(
                id=str(uuid.uuid4()), tenant_id=tenant_b.id,
                email=email_b, hashed_password=hashed_password,
                full_name="TechCorp User", is_active=True
            )
            session.add(user_b)
            await session.commit()
            print(f"Created user: {email_b}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed_data())
