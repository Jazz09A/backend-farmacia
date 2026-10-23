import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # Base
    # NOTE: env vars are read natively by pydantic-settings (same os.environ that
    # used to feed these redundant os.getenv() calls); the class defaults below only
    # apply when no env var is set.
    PROJECT_NAME: str = "FarmaPlus API"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # API URL
    API_URL: str = os.getenv("API_URL", "http://localhost:8000")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./db.sqlite3")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Pagination Settings
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    MIN_PAGE_SIZE: int = 1

    # CORS
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")

    # Email Settings
    SMTP_HOST: str | None = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int | None = 587
    SMTP_USER: str | None = os.getenv("SMTP_USER", "programatevzla@gmail.com")
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD", "crpg cagx zyyg hgys")
    SMTP_FROM: str | None = os.getenv("SMTP_FROM", "programatevzla@gmail.com")
    SMTP_FROM_NAME: str | None = os.getenv("SMTP_FROM_NAME", "Grupo Drozainka")

    # Frontend URL
    FRONTEND_URL: str | None = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # SourceSystem Database Configuration
    SOURCE_SYSTEM_SERVER: str | None = os.getenv("SOURCE_SYSTEM_SERVER", "localhost")
    SOURCE_SYSTEM_PORT: int | None = int(os.getenv("SOURCE_SYSTEM_PORT", "49571"))
    SOURCE_SYSTEM_DATABASE: str | None = os.getenv("SOURCE_SYSTEM_DATABASE", "GDROZAINK_A")
    SOURCE_SYSTEM_USER: str | None = os.getenv("SOURCE_SYSTEM_USER", None)
    SOURCE_SYSTEM_PASSWORD: str | None = os.getenv("SOURCE_SYSTEM_PASSWORD", None)

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

    # Cache Backend Configuration (Redis)
    # CACHE_DRIVER: 'memory' (default local/CI) o 'redis' (producción).
    # Con driver 'redis', si Redis falla se degrada a memoria automáticamente
    # y se reintenta cada CACHE_REDIS_HEALTH_INTERVAL segundos.
    CACHE_DRIVER: str = os.getenv("CACHE_DRIVER", "memory")  # 'memory' | 'redis'
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_REDIS_KEY_PREFIX: str = os.getenv("CACHE_REDIS_KEY_PREFIX", "farmacia:cache:")
    CACHE_REDIS_HEALTH_INTERVAL: int = int(os.getenv("CACHE_REDIS_HEALTH_INTERVAL", "30"))  # segundos

    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME: str | None = os.getenv("CLOUDINARY_CLOUD_NAME", None)
    CLOUDINARY_API_KEY: str | None = os.getenv("CLOUDINARY_API_KEY", None)
    CLOUDINARY_API_SECRET: str | None = os.getenv("CLOUDINARY_API_SECRET", None)

    # Feature flags (demo / temporal)
    # Permite habilitar filtros temporales sin comprometer el contrato final del API
    ENABLE_CLOUDINARY_IMAGES_ONLY_FILTER: bool = (
        os.getenv("ENABLE_CLOUDINARY_IMAGES_ONLY_FILTER", "False").lower() == "true"
    )

    class Config:
        env_file = ".env"
        case_sensitive = True
        # pydantic-settings >= 2.10 prohíbe campos extra del .env por defecto;
        # ignorarlos restaura el comportamiento anterior (ej: PORT, NGINX_...)
        extra = "ignore"
