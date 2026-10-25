from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_prefix="DATABASE_",
    )

    URL: str = Field(
        default="sqlite:///./db.sqlite3",
        description="SQLAlchemy database URL.",
    )


class SMTPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_prefix="SMTP_",
    )

    HOST: str = "smtp.gmail.com"
    PORT: int = Field(default=587, gt=0)
    USER: str | None = "programatevzla@gmail.com"
    PASSWORD: str = Field(
        ...,
        min_length=1,
        description="SMTP password. Required (no default).",
    )
    FROM: str | None = "programatevzla@gmail.com"
    FROM_NAME: str | None = "Grupo Drozainka"

    @field_validator("PORT")
    @classmethod
    def _validate_smtp_port(cls, v: int) -> int:
        if v <= 0 or v > 65535:
            raise ValueError("SMTP_PORT must be a valid TCP port (1-65535)")
        return v


class JWTSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="JWT signing secret. Required, min 32 chars.",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(..., gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def _validate_token_expire_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be > 0")
        return v


class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_prefix="CACHE_",
    )

    ENABLED: bool = True
    CATALOG_TTL: int = 1800
    DETAIL_TTL: int = 3600
    STATIC_TTL: int = 7200
    DEFAULT_TTL: int = 1800
    # Backend de cache (migración Redis con fallback a memoria).
    DRIVER: str = "memory"  # 'memory' | 'redis'
    REDIS_KEY_PREFIX: str = "farmacia:cache:"
    REDIS_HEALTH_INTERVAL: int = 30  # segundos


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    URL: str = "redis://localhost:6379/0"


class SourceSystemSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_prefix="SOURCE_",
    )

    SYSTEM_SERVER: str | None = "localhost"
    SYSTEM_PORT: int = Field(default=49571, gt=0)
    SYSTEM_DATABASE: str | None = "GDROZAINK_A"
    SYSTEM_USER: str | None = None
    SYSTEM_PASSWORD: str | None = None

    POOL_SIZE: int = Field(default=15, gt=0)
    MAX_OVERFLOW: int = Field(default=10, ge=0)
    POOL_TIMEOUT: int = Field(default=30, gt=0)
    POOL_RECYCLE: int = Field(default=300, gt=0)


class CloudinarySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_prefix="CLOUDINARY_",
    )

    CLOUD_NAME: str | None = None
    API_KEY: str | None = None
    API_SECRET: str | None = None
    ENABLE_IMAGES_ONLY_FILTER: bool = False


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "FarmaPlus API"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    APP_ENV: str = "development"
    CSP_POLICY: str | None = None
    API_URL: str = "http://localhost:8000"
    FRONTEND_URL: str | None = "http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    DEFAULT_PAGE_SIZE: int = Field(default=20, gt=0)
    MAX_PAGE_SIZE: int = Field(default=100, gt=0)
    MIN_PAGE_SIZE: int = Field(default=1, gt=0)

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


# Module-level settings instances (composed)
app = AppSettings()
database = DatabaseSettings()
smtp = SMTPSettings()  # type: ignore[call-arg]
jwt = JWTSettings()  # type: ignore[call-arg]
cache = CacheSettings()
redis = RedisSettings()
source_system = SourceSystemSettings()
cloudinary = CloudinarySettings()


# Backwards compatibility - single Settings object that composes sub-settings
class Settings:
    """Compatibility wrapper for code using `settings.X`"""

    def __init__(self):
        self.app = app
        self.database = database
        self.smtp = smtp
        self.jwt = jwt
        self.cache = cache
        self.redis = redis
        self.source_system = source_system
        self.cloudinary = cloudinary

        # Contrato plano de cache (migración Redis, `cache_service` consume
        # `settings.CACHE_*` / `settings.REDIS_URL` directamente).
        self.CACHE_ENABLED = cache.ENABLED
        self.CACHE_CATALOG_TTL = cache.CATALOG_TTL
        self.CACHE_DETAIL_TTL = cache.DETAIL_TTL
        self.CACHE_STATIC_TTL = cache.STATIC_TTL
        self.CACHE_DEFAULT_TTL = cache.DEFAULT_TTL
        self.CACHE_DRIVER = cache.DRIVER
        self.CACHE_REDIS_KEY_PREFIX = cache.REDIS_KEY_PREFIX
        self.CACHE_REDIS_HEALTH_INTERVAL = cache.REDIS_HEALTH_INTERVAL
        self.REDIS_URL = redis.URL


settings = Settings()
