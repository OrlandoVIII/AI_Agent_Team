import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from typing import AsyncGenerator

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_recycle=300,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except SQLAlchemyError as e:
                logger.error(f"Database session error: {e}")
                await session.rollback()
                raise HTTPException(status_code=500, detail="Database error")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
