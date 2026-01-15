"""app/config/settings.py

Configuration management using Pydantic BaseSettings.
Loads from environment variables and .env file.
"""

import os
from typing import Optional
try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""
    
    # Redis Configuration
    REDIS_HOST: str = Field(default="localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_URL: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    
    # IBKR Configuration
    IBKR_HOST: str = Field(default="127.0.0.1", env="IBKR_HOST")
    IBKR_PORT: int = Field(default=7497, env="IBKR_PORT")
    IBKR_CLIENT_ID: int = Field(default=1, env="IBKR_CLIENT_ID")
    
    # Engine Configuration
    WORKER_COUNT: int = Field(default=1, env="WORKER_COUNT")
    BATCH_SIZE: int = Field(default=20, env="BATCH_SIZE")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    # API Configuration
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    
    # Hammer Pro Configuration
    HAMMER_HOST: str = Field(default="127.0.0.1", env="HAMMER_HOST")
    HAMMER_PORT: int = Field(default=16400, env="HAMMER_PORT")
    HAMMER_PASSWORD: Optional[str] = Field(default=None, env="HAMMER_PASSWORD")
    HAMMER_ACCOUNT_KEY: str = Field(default="ALARIC:TOPI002240A7", env="HAMMER_ACCOUNT_KEY")
    
    # Monitoring (optional)
    METRICS_PORT: int = Field(default=8001, env="METRICS_PORT")
    
    # Optional fields that might be in .env but not always needed
    POLYGON_API_KEY: Optional[str] = Field(default=None, env="POLYGON_API_KEY")
    
    # Auto-load CSV on startup (default: True - CSV is loaded automatically at startup)
    AUTO_LOAD_CSV: bool = Field(default=True, env="AUTO_LOAD_CSV")
    
    # Pydantic v2 compatibility
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"  # Ignore extra fields from .env file
    }


# Global settings instance
# Note: .env file is loaded automatically by pydantic_settings
# Priority: CLI arg > environment variable > .env file > default
settings = Settings()

