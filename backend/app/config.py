import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # App settings
    PROJECT_NAME: str = "FastAPI Backend"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Database settings
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@db:5432/fastapi_db')
    DATABASE_ECHO: bool = False
    
    # CORS settings
    ALLOWED_HOSTS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Security settings - NO DEFAULT VALUES for secrets
    SECRET_KEY: str  # Must be set in environment
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # API settings
    API_V1_STR: str = "/api/v1"
    
    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")


settings = Settings()