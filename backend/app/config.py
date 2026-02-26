import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings.
    
    See .env.example for configuration template
    """
    
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
    
    # Database settings - NO DEFAULT for production security
    DATABASE_URL: str
    DATABASE_ECHO: bool = False
    
    # CORS settings
    ALLOWED_HOSTS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Security settings - NO DEFAULT VALUES for secrets
    SECRET_KEY: str  # Must be set in environment
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # API settings
    API_V1_STR: str = "/api/v1"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Validate SECRET_KEY is set and has sufficient length
        if not self.SECRET_KEY:
            raise ValueError('SECRET_KEY environment variable is required')
        
        if len(self.SECRET_KEY) < 32:
            raise ValueError('SECRET_KEY must be at least 32 characters long for security')
        
        # Validate DATABASE_URL is set
        if not self.DATABASE_URL:
            raise ValueError('DATABASE_URL environment variable is required')
    
    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")


settings = Settings()
