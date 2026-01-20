from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # Base
    PROJECT_NAME: str = "FarmaPlus API"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", True)
    
    # API URL
    API_URL: str = os.getenv("API_URL", "http://localhost:8000")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./db.sqlite3")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7)
    
    # Pagination Settings
    DEFAULT_PAGE_SIZE: int = os.getenv("DEFAULT_PAGE_SIZE", 20)
    MAX_PAGE_SIZE: int = os.getenv("MAX_PAGE_SIZE", 100)
    MIN_PAGE_SIZE: int = os.getenv("MIN_PAGE_SIZE", 1)
    
    # CORS
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
    
    # Email Settings - Resend
    RESEND_API_KEY: Optional[str] = os.getenv("RESEND_API_KEY", None)
    EMAIL_FROM: Optional[str] = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
    EMAIL_FROM_NAME: Optional[str] = os.getenv("EMAIL_FROM_NAME", "Grupo Drozainka")
    EMAIL_TEST: Optional[str] = os.getenv("EMAIL_TEST", "resend.dev@gmail.com")
    # Frontend URL
    FRONTEND_URL: Optional[str] = os.getenv("FRONTEND_URL", "http://localhost:5173")

    
    # SourceSystem Database Configuration
    SOURCE_SYSTEM_SERVER: Optional[str] = os.getenv("SOURCE_SYSTEM_SERVER", "localhost")
    SOURCE_SYSTEM_PORT: Optional[int] = int(os.getenv("SOURCE_SYSTEM_PORT", "49571"))
    SOURCE_SYSTEM_DATABASE: Optional[str] = os.getenv("SOURCE_SYSTEM_DATABASE", "GDROZAINK_A")
    SOURCE_SYSTEM_USER: Optional[str] = os.getenv("SOURCE_SYSTEM_USER", None)
    SOURCE_SYSTEM_PASSWORD: Optional[str] = os.getenv("SOURCE_SYSTEM_PASSWORD", None)
    
    # SourceSystem Connection Pool Configuration
    SOURCE_POOL_SIZE: int = int(os.getenv("SOURCE_POOL_SIZE", "15"))
    SOURCE_MAX_OVERFLOW: int = int(os.getenv("SOURCE_MAX_OVERFLOW", "10"))
    SOURCE_POOL_TIMEOUT: int = int(os.getenv("SOURCE_POOL_TIMEOUT", "30"))
    SOURCE_POOL_RECYCLE: int = int(os.getenv("SOURCE_POOL_RECYCLE", "300"))
    
    # Cache TTL Configuration (seconds)
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "True").lower() == "true"
    CACHE_CATALOG_TTL: int = int(os.getenv("CACHE_CATALOG_TTL", "1800"))  # 30 minutos
    CACHE_DETAIL_TTL: int = int(os.getenv("CACHE_DETAIL_TTL", "3600"))  # 60 minutos
    CACHE_STATIC_TTL: int = int(os.getenv("CACHE_STATIC_TTL", "7200"))  # 2 horas
    CACHE_DEFAULT_TTL: int = int(os.getenv("CACHE_DEFAULT_TTL", "1800"))  # 30 minutos por defecto
    
    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME: Optional[str] = os.getenv("CLOUDINARY_CLOUD_NAME", None)
    CLOUDINARY_API_KEY: Optional[str] = os.getenv("CLOUDINARY_API_KEY", None)
    CLOUDINARY_API_SECRET: Optional[str] = os.getenv("CLOUDINARY_API_SECRET", None)

    # Feature flags (demo / temporal)
    # Permite habilitar filtros temporales sin comprometer el contrato final del API
    ENABLE_CLOUDINARY_IMAGES_ONLY_FILTER: bool = (
        os.getenv("ENABLE_CLOUDINARY_IMAGES_ONLY_FILTER", "False").lower() == "true"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = True
