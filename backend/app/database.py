import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError, TimeoutError as SQLTimeoutError
from typing import AsyncGenerator
from fastapi import HTTPException

from app.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Create async engine with connection pool configuration
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.exception('Database error occurred during session')
                raise
            finally:
                await session.close()
    except DisconnectionError as e:
        logger.error(f'Database connection lost: {e}')
        raise HTTPException(status_code=503, detail='Database connection lost')
    except SQLTimeoutError as e:
        logger.error(f'Database timeout: {e}')
        raise HTTPException(status_code=504, detail='Database timeout')
    except SQLAlchemyError as e:
        logger.error(f'Database error: {e}')
        raise HTTPException(status_code=500, detail='Database unavailable')


async def create_tables():
    """
    Create database tables.
    
    Note: This function is primarily used for development and testing.
    Production deployments should use Alembic migrations instead for 
    proper database schema management and versioning.
    """
    try:
        from app.models.base import Base as ModelBase
        
        async with engine.begin() as conn:
            await conn.run_sync(ModelBase.metadata.create_all)
    except Exception as e:
        logger.error(f'Failed to create tables: {e}')
        raise


async def drop_tables():
    """
    Drop database tables.
    
    Warning: This function is destructive and should only be used in
    development or testing environments. Production deployments should
    use Alembic migrations for schema changes.
    """
    try:
        from app.models.base import Base as ModelBase
        
        async with engine.begin() as conn:
            await conn.run_sync(ModelBase.metadata.drop_all)
    except Exception as e:
        logger.error(f'Failed to drop tables: {e}')
        raise