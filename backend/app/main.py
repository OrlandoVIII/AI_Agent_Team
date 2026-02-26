import logging
import sys
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import engine, AsyncSessionLocal
from app.models.base import Base
from app.utils.retry import retry_with_exponential_backoff

# Configure logging with environment variables
def setup_logging():
    """Setup logging with environment variables to control destinations."""
    log_level = os.getenv('LOG_LEVEL', 'INFO' if settings.is_production else 'DEBUG')
    log_to_file = os.getenv('LOG_TO_FILE', 'false').lower() == 'true'
    
    log_handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_to_file:
        try:
            log_dir = '/app/logs' if settings.is_production else '.'
            if settings.is_production:
                os.makedirs(log_dir, mode=0o755, exist_ok=True)
            log_handlers.append(logging.FileHandler(f'{log_dir}/app.log'))
        except (OSError, PermissionError) as e:
            if settings.is_production:
                raise RuntimeError(f'Cannot create production log file: {e}')
            logging.warning(f"Could not create log file: {e}. Using console only.")
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=log_handlers
    )

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Set third-party loggers to WARNING level to reduce noise
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


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