from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # Base
    PROJECT_NAME: str = "FarmaPlus API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    # DATABASE_URL: str = "postgresql://farmaplus:password@localhost:5432/farmaplus"
    DATABASE_URL: str = "sqlite:///./db.sqlite3"
    # Security
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:3001"]
    
    # Email
    SMTP_HOST: Optional[str] = "smtp.gmail.com"
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    
    # File Upload
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5MB
    
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

# Create uploads directory if it doesn't exist
def create_upload_dir():
    settings = Settings()
    if not os.path.exists(settings.UPLOAD_DIR):
        os.makedirs(settings.UPLOAD_DIR)

settings = Settings()
create_upload_dir() 