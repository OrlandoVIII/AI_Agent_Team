from pydantic import Field
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/backend_db",
        description="PostgreSQL database URL with asyncpg driver"
    )
    
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Backend API"
    
    # Security
    SECRET_KEY: str = Field(
        default="your-secret-key-change-this-in-production",
        description="Secret key for JWT token generation"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # CORS
    ALLOWED_HOSTS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="List of allowed origins for CORS"
    )
    
    # Environment
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
