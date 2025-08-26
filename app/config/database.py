from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config.settings import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Function to create all tables
def create_tables():
    # Import all models to ensure they are registered with Base
    from app.models import (
        User, Product, CartItem, Address, UserPreferences,
        Order, OrderItem, OrderAddress, Review, Category, Brand,
        FlashOffer, PromotionalCode, PromotionUsage, SupportTicket,
        SupportResponse, UserNotification, BlogCategory, BlogPost,
        ShippingZone, BlogCategory, BlogPost
    )
    Base.metadata.create_all(bind=engine) 