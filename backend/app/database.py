import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from typing import AsyncGenerator
import asyncpg.exceptions

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Create async engine with connection pool configuration from settings
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_recycle=settings.POOL_RECYCLE,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
)

# Create session factory with timeout configuration from settings
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


def map_db_error(e: Exception) -> HTTPException:
    """Map database errors to appropriate HTTP exceptions."""
    if settings.is_production:
        # In production, return generic error messages to avoid leaking details
        logger.error(f"Database error: {e}")
        if isinstance(e, (asyncpg.exceptions.ConnectionDoesNotExistError, 
                         asyncpg.exceptions.ConnectionFailureError)):
            return HTTPException(status_code=503, detail="Service temporarily unavailable")
        else:
            return HTTPException(status_code=500, detail="Internal server error")
    else:
        # In development, sanitize error messages to prevent schema information leakage
        if isinstance(e, asyncpg.exceptions.ConnectionDoesNotExistError):
            logger.error(f"Database connection does not exist: {e}")
            return HTTPException(status_code=503, detail="Connection error")
        elif isinstance(e, asyncpg.exceptions.PostgresError):
            logger.error(f"PostgreSQL error: {e}")
            return HTTPException(status_code=500, detail="Query error")
        elif isinstance(e, SQLAlchemyError):
            logger.error(f"Database session error: {e}")
            return HTTPException(status_code=500, detail="Database error")
        else:
            logger.error(f"Database connection failed: {e}")
            return HTTPException(status_code=503, detail="Database unavailable")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session with error handling and timeout."""
    try:
        async with asyncio.wait_for(AsyncSessionLocal(), timeout=settings.POOL_TIMEOUT) as session:
            try:
                yield session
            except SQLAlchemyError as e:
                logger.error(f"Database session error: {e}")
                await session.rollback()
                raise HTTPException(status_code=500, detail="Database error")
    except asyncio.TimeoutError:
        logger.error("Database connection timeout")
        raise HTTPException(status_code=503, detail="Database timeout")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
