from pydantic_settings import BaseSettings
from typing import Optional, List
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
    # DATABASE_URL: str = "postgresql://farmaplus:password@localhost:5432/farmaplus"
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
    
    # Email Settings
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: Optional[int] = os.getenv("SMTP_PORT", 587)
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER", "programatevzla@gmail.com")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD", "crpg cagx zyyg hgys")
    SMTP_FROM: Optional[str] = os.getenv("SMTP_FROM", "programatevzla@gmail.com")
    SMTP_FROM_NAME: Optional[str] = os.getenv("SMTP_FROM_NAME", "Grupo Drozainka")
    
    # Currency API
    CURRENCY_API_KEY: Optional[str] = None
    
    # Payment Gateways
    STRIPE_SECRET_KEY: Optional[str] = None
    PAYPAL_CLIENT_ID: Optional[str] = None
    PAYPAL_CLIENT_SECRET: Optional[str] = None
    
    # Venezuelan Payment Methods
    BANESCO_API_KEY: Optional[str] = None
    MERCANTIL_API_KEY: Optional[str] = None
    
    # Frontend URL
    FRONTEND_URL: Optional[str] = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None
    CLOUDINARY_UPLOAD_PRESET: Optional[str] = None
    
    # SourceSystem Database Configuration
    SOURCE_SYSTEM_SERVER: Optional[str] = os.getenv("SOURCE_SYSTEM_SERVER", "localhost")
    SOURCE_SYSTEM_PORT: Optional[int] = int(os.getenv("SOURCE_SYSTEM_PORT", "49571"))
    SOURCE_SYSTEM_DATABASE: Optional[str] = os.getenv("SOURCE_SYSTEM_DATABASE", "GDROZAINK_A")
    SOURCE_SYSTEM_USER: Optional[str] = os.getenv("SOURCE_SYSTEM_USER", None)
    SOURCE_SYSTEM_PASSWORD: Optional[str] = os.getenv("SOURCE_SYSTEM_PASSWORD", None)
    
    class Config:
        env_file = ".env"
        case_sensitive = True
