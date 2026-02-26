import os
import re
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    # Project Info
    PROJECT_NAME: str = "FastAPI Backend"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "FastAPI Backend API"
    API_V1_STR: str = "/api/v1"
    
    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True
    
    # CORS Settings
    ALLOWED_HOSTS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Database Settings - REQUIRED, no default
    DATABASE_URL: str
    DATABASE_ECHO: bool = False
    
    # Security Settings - REQUIRED, no default
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Environment
    ENVIRONMENT: str = "development"
    
    def __init__(self, **kwargs):
        # Get from environment if not provided
        if 'SECRET_KEY' not in kwargs:
            kwargs['SECRET_KEY'] = os.getenv('SECRET_KEY')
        if 'DATABASE_URL' not in kwargs:
            kwargs['DATABASE_URL'] = os.getenv('DATABASE_URL')
        
        if not kwargs.get('SECRET_KEY'):
            raise ValueError("SECRET_KEY environment variable is required")
        if not kwargs.get('DATABASE_URL'):
            raise ValueError("DATABASE_URL environment variable is required")
        
        super().__init__(**kwargs)
    
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v:
            raise ValueError("SECRET_KEY is required")
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v
    
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL is required")
        return v
    
    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v):
        """Parse ALLOWED_HOSTS from environment variable or use default."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",") if host.strip()]
        return v or ["http://localhost:3000", "http://localhost:8000"]
    
    @property
    def is_development(self) -> bool:
        """Check if environment is development."""
        return self.ENVIRONMENT.lower() in ("development", "dev")
    
    @property
    def is_production(self) -> bool:
        """Check if environment is production."""
        return self.ENVIRONMENT.lower() in ("production", "prod")
    
    def __repr__(self) -> str:
        """Redact sensitive values from string representation."""
        return f"<Settings(DATABASE_URL='[REDACTED]', SECRET_KEY='[REDACTED]')>"


settings = Settings()