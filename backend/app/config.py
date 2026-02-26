import os
from typing import List
from pydantic import Field
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
    PROJECT_NAME: str = Field(default="FastAPI Backend")
    VERSION: str = Field(default="0.1.0")
    DESCRIPTION: str = Field(default="FastAPI Backend API")
    API_V1_STR: str = Field(default="/api/v1")
    
    # Server Settings
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    RELOAD: bool = Field(default=True)
    
    # CORS Settings
    ALLOWED_HOSTS: List[str] = Field(default=["*"])
    
    # Database Settings
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/fastapi_db"
    )
    DATABASE_ECHO: bool = Field(default=False)
    
    # Security Settings
    SECRET_KEY: str = Field(
        default="your-secret-key-change-this-in-production"
    )
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    
    # Environment
    ENVIRONMENT: str = Field(default="development")
    
    @property
    def is_development(self) -> bool:
        """Check if environment is development."""
        return self.ENVIRONMENT.lower() in ("development", "dev")
    
    @property
    def is_production(self) -> bool:
        """Check if environment is production."""
        return self.ENVIRONMENT.lower() in ("production", "prod")


settings = Settings()
