from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "FarmaPlus API"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    API_URL: str = "http://localhost:8000"

    DATABASE_URL: str = Field(
        default="sqlite:///./db.sqlite3",
        description="SQLAlchemy database URL.",
    )

    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="JWT signing secret. Required, min 32 chars.",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(..., gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)

    DEFAULT_PAGE_SIZE: int = Field(default=20, gt=0)
    MAX_PAGE_SIZE: int = Field(default=100, gt=0)
    MIN_PAGE_SIZE: int = Field(default=1, gt=0)

    ALLOWED_ORIGINS: str = "http://localhost:5173"

    SMTP_HOST: Optional[str] = "smtp.gmail.com"
    SMTP_PORT: int = Field(default=587, gt=0)
    SMTP_USER: Optional[str] = "programatevzla@gmail.com"
    SMTP_PASSWORD: str = Field(
        ...,
        min_length=1,
        description="SMTP password. Required (no default).",
    )
    SMTP_FROM: Optional[str] = "programatevzla@gmail.com"
    SMTP_FROM_NAME: Optional[str] = "Grupo Drozainka"

    FRONTEND_URL: Optional[str] = "http://localhost:5173"

    SOURCE_SYSTEM_SERVER: Optional[str] = "localhost"
    SOURCE_SYSTEM_PORT: int = Field(default=49571, gt=0)
    SOURCE_SYSTEM_DATABASE: Optional[str] = "GDROZAINK_A"
    SOURCE_SYSTEM_USER: Optional[str] = None
    SOURCE_SYSTEM_PASSWORD: Optional[str] = None

    SOURCE_POOL_SIZE: int = Field(default=15, gt=0)
    SOURCE_MAX_OVERFLOW: int = Field(default=10, ge=0)
    SOURCE_POOL_TIMEOUT: int = Field(default=30, gt=0)
    SOURCE_POOL_RECYCLE: int = Field(default=300, gt=0)

    CACHE_ENABLED: bool = True
    CACHE_CATALOG_TTL: int = 1800
    CACHE_DETAIL_TTL: int = 3600
    CACHE_STATIC_TTL: int = 7200
    CACHE_DEFAULT_TTL: int = 1800

    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    ENABLE_CLOUDINARY_IMAGES_ONLY_FILTER: bool = False

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def _validate_token_expire_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be > 0")
        return v

    @field_validator("SMTP_PORT")
    @classmethod
    def _validate_smtp_port(cls, v: int) -> int:
        if v <= 0 or v > 65535:
            raise ValueError("SMTP_PORT must be a valid TCP port (1-65535)")
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
