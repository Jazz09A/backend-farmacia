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

from main import app
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
    """Test user data for natural user registration."""
    return {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "cedula": "V12345678",
        "password": "TestPassword123",
        "phone": "+58414123456",
        "preferred_currency": "VES",
        "birth_date": "1990-01-01",
        "address": "Av. Principal 123, Caracas"
    }

@pytest.fixture
def test_user_data_juridico():
    """Test user data for juridico user registration."""
    return {
        "email": "empresa@test.com",
        "company_name": "Farmacia Test S.A.",
        "rif": "J123456789",
        "registro_mercantil": "RM-12345",
        "representante_legal_cedula": "V87654321",
        "representante_legal_nombre": "Juan Pérez",
        "referencia_comercial_proveedor": "Proveedor ABC C.A.",
        "referencia_bancaria": "Banco Provincial",
        "direccion_establecimiento": "Av. Comercial 456, Valencia",
        "password": "EmpresaPass456",
        "phone": "+58212987654",
        "preferred_currency": "USD",
        "dueno_telefono": "+58414987654",
        "dueno_email": "dueno@empresa.com",
        "codigo_sicm": "SICM123456"
    }

@pytest.fixture
def test_user(db: Session):
    """Create a test natural user in the database."""
    user_data = {
        "email": "testuser@example.com",
        "first_name": "Test",
        "last_name": "User",
        "cedula": "V12345678",
        "hashed_password": get_password_hash("testpass123"),
        "user_type": "natural",
        "phone": "+58414123456",
        "preferred_currency": "VES",
        "is_active": True,
        "is_verified": True,
        "address": "Av. Test 123, Caracas"
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
def test_juridico_user(db: Session):
    """Create a test juridico user in the database."""
    user_data = {
        "email": "farmacia@example.com",
        "company_name": "Farmacia Test S.A.",
        "rif": "J987654321",
        "registro_mercantil": "RM-67890",
        "representante_legal_cedula": "V11111111",
        "representante_legal_nombre": "María García",
        "referencia_comercial_proveedor": "Proveedor XYZ C.A.",
        "referencia_bancaria": "Banco Test",
        "direccion_establecimiento": "Av. Test Comercial 789, Maracay",
        "hashed_password": get_password_hash("farmaciapass123"),
        "user_type": "juridico",
        "phone": "+58212123456",
        "preferred_currency": "USD",
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
        preferred_currency="USD"
    )
    db.add(preferences)
    db.commit()
    
    return user

@pytest.fixture
def test_admin_user(db: Session):
    """Create a test admin user in the database."""
    user_data = {
        "email": "admin@example.com",
        "first_name": "Admin",
        "last_name": "User",
        "cedula": "V99999999",
        "hashed_password": get_password_hash("adminpass123"),
        "user_type": "natural",
        "phone": "+58414999999",
        "is_active": True,
        "is_verified": True,
        "role": "admin"
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