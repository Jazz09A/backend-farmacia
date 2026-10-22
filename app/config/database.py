from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings

settings = Settings()
# Create SQLAlchemy engine
engine = create_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=300)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
# NOTE: `declarative_base()` imported from the deprecated `sqlalchemy.ext.declarative`
# shim resolves to Any for type checkers (SQLAlchemy 2.0 ships no typing for this
# legacy entrypoint), so classes inheriting from `Base` need
# `# type: ignore[valid-type, misc]` until models migrate to the 2.0 `DeclarativeBase`
# / `mapped_column` style.
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
    Base.metadata.create_all(bind=engine)
