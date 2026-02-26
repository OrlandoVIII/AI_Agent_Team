import os
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
    
    # Database Settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/fastapi_db"
    DATABASE_ECHO: bool = False
    
    # Security Settings
    SECRET_KEY: str = "change-me-in-production-must-be-32-chars-minimum"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Environment
    ENVIRONMENT: str = "development"
    
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v
    
    @field_validator("DATABASE_URL")
    @classmethod
    def redact_db_credentials(cls, v: str) -> str:
        """Redact credentials from string representation to prevent logging exposure."""
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