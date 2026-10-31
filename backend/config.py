from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List
import os

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-lite-latest"
    DATABASE_URL: str = "sqlite:///./claimlens.db"
    UPLOAD_DIR: str = "./uploads"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:8000", "*"]
    OPEN_METEO_BASE_URL: str = "https://archive-api.open-meteo.com/v1/archive"

    # Authentication & Security
    JWT_SECRET: str = Field(default="")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # Set to True in production with HTTPS

    # Demo Staff Credentials (for seed_users.py)
    DEMO_ADJUSTER_PASSWORD: str = "AdjusterSecurePass1!"
    DEMO_SUPERVISOR_PASSWORD: str = "SupervisorSecurePass1!"
    DEMO_ADMIN_PASSWORD: str = "AdminSecurePass1!"

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        # If not set in test or dev, generate or require strong secret
        if not v or len(v.strip()) < 32:
            raise ValueError(
                "CRITICAL SECURITY CONFIGURATION ERROR: JWT_SECRET must be set in .env "
                "and must be at least 32 characters long. Refusing to start."
            )
        return v.strip()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
