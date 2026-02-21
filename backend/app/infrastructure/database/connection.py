"""
Async SQLAlchemy engine and session factory.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine_kwargs = {}
if not str(settings.database_url).startswith("sqlite"):
    engine_kwargs = {
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
    }

engine = create_async_engine(
    str(settings.database_url),
    echo=False,
    **engine_kwargs
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def create_task_session_factory():
    """
    Create a FRESH async engine + session factory for use inside Celery tasks.
    This avoids the 'attached to a different loop' error caused by the global
    engine being bound to the parent process's (now-closed) event loop.
    """
    task_engine = create_async_engine(
        str(settings.database_url),
        echo=False,
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,
    )
    return async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_async_session() -> AsyncSession:
    """Dependency-injection helper — yields a scoped session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
