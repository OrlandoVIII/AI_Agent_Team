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

from app.config import settings
from app.database import engine, AsyncSessionLocal
from app.models.base import Base

# Configure logging with robust file handler
log_handlers = [logging.StreamHandler(sys.stdout)]

if settings.is_production:
    # Use fixed absolute path for security
    log_dir = '/var/log/app'
    try:
        os.makedirs(log_dir, mode=0o750, exist_ok=True)
        log_handlers.append(logging.FileHandler(f'{log_dir}/app.log'))
        logging.info(f"Log directory created successfully at {log_dir}")
    except (OSError, PermissionError) as e:
        # In production, fail fast if proper log directory cannot be created
        if settings.is_production and not log_handlers[1:]:  # Only stdout handler exists
            raise RuntimeError(f'Cannot create production log directory: {e}')
        logging.warning(f"Could not create log directory {log_dir}: {e}. Falling back to current directory.")
        try:
            log_handlers.append(logging.FileHandler('app.log'))
        except Exception as fallback_error:
            logging.error(f"Could not create fallback log file: {fallback_error}")
            if settings.is_production:
                raise RuntimeError('Cannot create production log directory')

logging.basicConfig(
    level=logging.INFO if settings.is_production else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=log_handlers
)

logger = logging.getLogger(__name__)

# Set third-party loggers to WARNING level to reduce noise
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def create_tables():
    """Create database tables with retry logic and jitter."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except SQLAlchemyError as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Database creation attempt {attempt + 1} failed: {e}. Retrying...")
            # Exponential backoff with jitter to prevent thundering herd
            await asyncio.sleep(2 ** attempt + random.uniform(0, 1))


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
