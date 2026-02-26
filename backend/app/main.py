import logging
import sys
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import asyncio
import random
from typing import Callable, Awaitable, TypeVar

from app.config import settings
from app.database import engine, AsyncSessionLocal
from app.models.base import Base

# Type variable for the retry function
T = TypeVar('T')

# Configure logging with comprehensive error handling and fallbacks
def setup_logging():
    """Setup logging with comprehensive error handling and fallbacks."""
    log_handlers = [logging.StreamHandler(sys.stdout)]
    
    try:
        if settings.is_production:
            # Use more restrictive permissions
            log_dir = '/var/log/app'
            try:
                os.makedirs(log_dir, mode=0o700, exist_ok=True)
                log_handlers.append(logging.FileHandler(f'{log_dir}/app.log'))
                logging.info(f"Log directory created successfully at {log_dir}")
            except OSError as e:
                # Handle file system errors specifically
                if settings.is_production:
                    raise RuntimeError(f'Cannot create production log directory due to OS error: {e}')
                logging.warning(f"OS error creating log directory {log_dir}: {e}. Falling back to current directory.")
                try:
                    log_handlers.append(logging.FileHandler('app.log'))
                except OSError as fallback_error:
                    logging.error(f"OS error creating fallback log file: {fallback_error}")
                    if settings.is_production:
                        raise RuntimeError('Cannot create production log directory or fallback')
            except PermissionError as e:
                # Handle permission errors specifically
                if settings.is_production:
                    raise RuntimeError(f'Cannot create production log directory due to permission error: {e}')
                logging.warning(f"Permission error creating log directory {log_dir}: {e}. Falling back to current directory.")
                try:
                    log_handlers.append(logging.FileHandler('app.log'))
                except PermissionError as fallback_error:
                    logging.error(f"Permission error creating fallback log file: {fallback_error}")
                    if settings.is_production:
                        raise RuntimeError('Cannot create production log directory or fallback due to permissions')
    except Exception as e:
        # Final fallback: ensure critical errors are always visible
        logging.error(f"Critical logging setup error: {e}")
        if settings.is_production:
            # In production, we must have proper logging
            raise RuntimeError(f"Critical logging setup failure in production: {e}")
        else:
            # In development, warn but continue with console logging only
            logging.warning("Falling back to console logging only due to setup errors")
    
    # Final validation to ensure at least one log handler is configured
    if not log_handlers:
        raise RuntimeError('No log handlers configured')
    
    logging.basicConfig(
        level=logging.INFO if settings.is_production else logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=log_handlers
    )

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Set third-party loggers to WARNING level to reduce noise
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def retry_with_exponential_backoff(func: Callable[[], Awaitable[T]], max_retries: int = 3, base_delay: int = 1, max_delay: int = 60) -> T:
    """
    Retry function with exponential backoff and jitter.
    
    Args:
        func: Async function to retry
        max_retries: Maximum retry attempts (default 3)
        base_delay: Base delay in seconds (default 1)
        max_delay: Maximum delay in seconds (default 60)
        
    Returns:
        Result of the function call
        
    Raises:
        Exception: The last exception encountered if all retries fail
        
    The function implements exponential backoff with jitter to prevent
    thundering herd problems when multiple instances retry simultaneously.
    """
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Operation attempt {attempt + 1} failed: {e}. Retrying...")
            # Exponential backoff with jitter to prevent thundering herd
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
            await asyncio.sleep(delay)


async def create_tables():
    """Create database tables with retry logic and jitter."""
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    await retry_with_exponential_backoff(_create)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with proper error handling."""
    try:
        await create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        raise
    yield
    logger.info("Application shutting down")
    # Cleanup on shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint with database connectivity check."""
    try:
        # Check database connectivity
        async with AsyncSessionLocal() as session:
            await session.execute(text('SELECT 1'))
        
        return JSONResponse(
            content={
                "status": "healthy",
                "service": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "database": "connected"
            }
        )
    except SQLAlchemyError as e:
        logger.error(f"Health check database error: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="Service unavailable - database connection failed"
        )
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="Service unavailable"
        )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "version": settings.VERSION,
        "docs": "/docs"
    }