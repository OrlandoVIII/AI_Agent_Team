import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError, TimeoutError as SQLTimeoutError
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
    connect_args={'connect_timeout': settings.DATABASE_CONNECT_TIMEOUT}
)

# Create session factory with timeout configuration from settings
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session with specific error handling and timeout."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except asyncpg.exceptions.UniqueViolationError as e:
                logger.error(f"Database constraint violation: {e}")
                await session.rollback()
                raise HTTPException(status_code=409, detail="Data conflict - resource already exists")
            except asyncpg.exceptions.ForeignKeyViolationError as e:
                logger.error(f"Database foreign key violation: {e}")
                await session.rollback()
                raise HTTPException(status_code=422, detail="Invalid reference - related resource not found")
            except asyncpg.exceptions.NotNullViolationError as e:
                logger.error(f"Database not null violation: {e}")
                await session.rollback()
                raise HTTPException(status_code=400, detail="Missing required field")
            except SQLTimeoutError as e:
                logger.error(f"Database timeout: {e}")
                await session.rollback()
                raise HTTPException(status_code=408, detail="Database operation timeout")
            except DisconnectionError as e:
                logger.error(f"Database disconnection: {e}")
                await session.rollback()
                raise HTTPException(status_code=503, detail="Database connection lost")
            except SQLAlchemyError as e:
                logger.error(f"Database session error: {e}")
                await session.rollback()
                raise HTTPException(status_code=500, detail="Database error")
    except asyncpg.exceptions.InvalidAuthorizationSpecificationError as e:
        logger.error(f"Database authentication failed: {e}")
        raise HTTPException(status_code=503, detail="Database authentication failed")
    except asyncpg.exceptions.CannotConnectNowError as e:
        logger.error(f"Database connection rejected: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")