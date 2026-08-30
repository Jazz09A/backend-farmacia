from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config.settings import Settings

settings = Settings()

_engine_kwargs: dict = {}
if not settings.database.URL.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=300,
    )
elif settings.database.URL.startswith("sqlite"):
    # SQLite no soporta pool_size/max_overflow; usar StaticPool en tests
    # (vía conftest) o NullPool en runtime.
    from sqlalchemy.pool import NullPool

    _engine_kwargs["poolclass"] = NullPool

# Create SQLAlchemy engine
engine = create_engine(settings.database.URL, **_engine_kwargs)

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

# Function to create all tables (idempotente, no toca tablas existentes)
def create_tables():
    """
    Crea las tablas solo si la BD está vacía.
    Si ya existen tablas (migradas con Alembic), no hace nada.
    Esto evita sobrescribir accidentalmente un esquema migrado.
    """
    # Import all models to ensure they are registered with Base
    from app.models import (
        User, Product, CartItem, Address, UserPreferences,
        Category, Brand, FlashOffer, PromotionalCode,
        PromotionUsage, UserFavorite, CreditPayment,
        BlogPost, BlogCategory, BlogImage, ProductImage
    )
    inspector = inspect(engine)
    if inspector.get_table_names():
        # BD ya inicializada (probablemente vía Alembic) -> no tocar
        return False
    Base.metadata.create_all(bind=engine)
    return True