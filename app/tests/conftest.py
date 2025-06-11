"""
Configuración de pytest y fixtures compartidos para testing
"""

import pytest
import asyncio
from typing import Generator, AsyncGenerator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.config.database import get_db, Base
from app.config.settings import settings
from app.core.security import create_access_token, get_password_hash
from app.models import User, UserPreferences

# Test database URL (SQLite in memory)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Create test database engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """
    Create a fresh database for each test function.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """
    Create a test client that uses the override_get_db fixture to return a session.
    """
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()

@pytest.fixture
def test_user_data():
    """Test user data for registration."""
    return {
        "email": "test@example.com",
        "name": "Test User",
        "password": "TestPassword123",
        "confirm_password": "TestPassword123",
        "user_type": "natural",
        "phone": "+58414123456",
        "preferred_currency": "VES"
    }

@pytest.fixture
def test_user_data_juridico():
    """Test user data for juridico registration."""
    return {
        "email": "empresa@test.com",
        "name": "Empresa Test S.A.",
        "password": "EmpresaPass456",
        "confirm_password": "EmpresaPass456",
        "user_type": "juridico",
        "phone": "+58212987654",
        "preferred_currency": "USD"
    }

@pytest.fixture
def test_user(db: Session):
    """Create a test user in the database."""
    user_data = {
        "email": "testuser@example.com",
        "name": "Test User",
        "hashed_password": get_password_hash("testpass123"),
        "user_type": "natural",
        "phone": "+58414123456",
        "preferred_currency": "VES",
        "is_active": True,
        "is_verified": True
    }
    
    user = User(**user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create user preferences
    preferences = UserPreferences(
        user_id=user.id,
        preferred_currency="VES"
    )
    db.add(preferences)
    db.commit()
    
    return user

@pytest.fixture
def test_admin_user(db: Session):
    """Create a test admin user in the database."""
    user_data = {
        "email": "admin@example.com",
        "name": "Admin User",
        "hashed_password": get_password_hash("adminpass123"),
        "user_type": "natural",
        "is_active": True,
        "is_verified": True,
        "is_admin": True
    }
    
    user = User(**user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user

@pytest.fixture
def access_token(test_user: User):
    """Create access token for test user."""
    return create_access_token(data={"sub": test_user.email})

@pytest.fixture
def admin_access_token(test_admin_user: User):
    """Create access token for admin user."""
    return create_access_token(data={"sub": test_admin_user.email})

@pytest.fixture
def auth_headers(access_token: str):
    """Create authorization headers with access token."""
    return {"Authorization": f"Bearer {access_token}"}

@pytest.fixture
def admin_auth_headers(admin_access_token: str):
    """Create authorization headers with admin access token."""
    return {"Authorization": f"Bearer {admin_access_token}"}

@pytest.fixture
def test_login_data():
    """Test login credentials."""
    return {
        "email": "testuser@example.com",
        "password": "testpass123"
    }

@pytest.fixture
def invalid_login_data():
    """Invalid login credentials for testing authentication failures."""
    return {
        "email": "wrong@example.com",
        "password": "wrongpassword"
    }

# Sample data fixtures for future use
@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return {
        "name": "Paracetamol 500mg",
        "brand": "Farmatodo",
        "category": "Analgésicos",
        "subcategory": "Dolor y Fiebre",
        "patology": "Dolor de cabeza",
        "price_ves": 15000.0,
        "price_ref": 5.0,
        "description": "Medicamento para aliviar el dolor y reducir la fiebre",
        "ingredients": ["Paracetamol"],
        "image": "https://example.com/paracetamol.jpg",
        "images": ["https://example.com/paracetamol.jpg"],
        "in_stock": True,
        "stock": 100,
        "prescription": False,
        "dosage": "500mg",
        "presentation": "Tabletas",
        "laboratorio": "Laboratorio Test"
    }

@pytest.fixture
def sample_order_data():
    """Sample order data for testing."""
    return {
        "payment_method": "credit_card",
        "currency": "VES",
        "items": [
            {
                "product_id": "test-product-id",
                "quantity": 2,
                "selected_presentation": "Tabletas"
            }
        ],
        "shipping_address": {
            "street": "Av. Principal 123",
            "city": "Caracas",
            "state": "Distrito Capital",
            "country": "Venezuela",
            "recipient_name": "Test User",
            "recipient_phone": "+58414123456"
        }
    } 