from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # Base
    PROJECT_NAME: str = "FarmaPlus API"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Database
    # DATABASE_URL: str = "postgresql://farmaplus:password@localhost:5432/farmaplus"
    DATABASE_URL: str = "sqlite:///./db.sqlite3"
    
    # Security
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Pagination Settings
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    MIN_PAGE_SIZE: int = 1
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:3001"]
    
    # Email Settings
    SMTP_HOST: Optional[str] = "smtp.gmail.com"
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = "programatevzla@gmail.com"
    SMTP_PASSWORD: Optional[str] = "crpg cagx zyyg hgys"
    SMTP_FROM: Optional[str] = "programatevzla@gmail.com"
    SMTP_FROM_NAME: Optional[str] = "Grupo Drozainka"
    
    # Currency API
    CURRENCY_API_KEY: Optional[str] = None
    
    # Payment Gateways
    STRIPE_SECRET_KEY: Optional[str] = None
    PAYPAL_CLIENT_ID: Optional[str] = None
    PAYPAL_CLIENT_SECRET: Optional[str] = None
    
    # Venezuelan Payment Methods
    BANESCO_API_KEY: Optional[str] = None
    MERCANTIL_API_KEY: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
