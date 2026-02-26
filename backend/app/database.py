import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

from app.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    future=True,
    pool_pre_ping=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.exception('Database error occurred during session')
            raise
        finally:
            await session.close()


async def create_tables():
    """
    Create database tables.
    
    Note: This function is primarily used for development and testing.
    Production deployments should use Alembic migrations instead for 
    proper database schema management and versioning.
    """
    from app.models.base import Base as ModelBase
    
    async with engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)


async def drop_tables():
    """
    Drop database tables.
    
    Warning: This function is destructive and should only be used in
    development or testing environments. Production deployments should
    use Alembic migrations for schema changes.
    """
    from app.models.base import Base as ModelBase
    
    async with engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.drop_all)