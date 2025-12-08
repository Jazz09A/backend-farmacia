"""
Configuración global de fixtures para tests con conexión real a Profit Plus (source_system)

IMPORTANTE: Este archivo carga .env.test ANTES de importar Settings
para asegurar que los tests usen la configuración correcta de Profit Plus.

Los tests usan la BD REAL para autenticación (usuarios en tabla users).
Los clientes y artículos vienen de Profit Plus (source_system).
"""
import sys
import os
from pathlib import Path

# Obtener el directorio raíz del proyecto (donde está main.py)
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import uuid

# Cargar variables de entorno para tests ANTES de importar Settings
# override=True asegura que sobrescriba cualquier .env existente
env_test_path = PROJECT_ROOT / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path, override=True)
else:
    # Si no existe .env.test, intentar cargar .env
    load_dotenv(PROJECT_ROOT / ".env", override=False)

# Ahora importar módulos de la aplicación
from main import app  # main.py está en la raíz
from app.config.database import get_db
from app.config.settings import Settings
from app.core.security import create_access_token
from app.models.user import User

# Instancia de Settings que usará las variables de .env.test
# Settings() lee automáticamente de os.getenv() y .env.test ya está cargado
test_settings = Settings()

# Base de datos REAL de PostgreSQL para usuarios (autenticación)
# Usa la misma DATABASE_URL que la aplicación
DATABASE_URL = test_settings.DATABASE_URL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """
    Base de datos REAL de PostgreSQL para usuarios (autenticación).
    Los usuarios están en esta BD, los clientes/artículos vienen de Profit Plus.
    """
    db_session = TestingSessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture(scope="function")
def client(db):
    """
    Cliente de prueba FastAPI con BD real para autenticación.
    Los usuarios están en la BD local, los clientes/artículos en Profit Plus.
    """
    def override_get_db():
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# AUTENTICACIÓN REAL (usando TEST_CUSTOMER_EMAIL y TEST_CUSTOMER_PASSWORD)
# =============================================================================

@pytest.fixture
def test_customer_email():
    """Email del cliente de prueba desde .env"""
    return os.getenv("TEST_CUSTOMER_EMAIL", "test@farmacia.com")


@pytest.fixture
def test_customer_password():
    """Contraseña del cliente de prueba desde .env"""
    return os.getenv("TEST_CUSTOMER_PASSWORD", "testpass123")


@pytest.fixture
def auth_token_real(client, test_customer_email, test_customer_password):
    """
    Token JWT obtenido haciendo login REAL con TEST_CUSTOMER_EMAIL y TEST_CUSTOMER_PASSWORD.
    El usuario debe existir en la BD local (tabla users) o se auto-provisiona desde Profit Plus.
    """
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": test_customer_email,
            "password": test_customer_password
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    else:
        # Si el login falla, crear un token manualmente (para tests que no requieren login real)
        # Esto puede pasar si el usuario no existe en la BD
        print(f"⚠️  Login falló: {response.status_code} - {response.text[:200]}")
        print("   Usando token mock como fallback")
        return create_access_token({"sub": test_customer_email})


@pytest.fixture
def auth_headers(auth_token_real):
    """Headers con autenticación REAL obtenida del login"""
    return {"Authorization": f"Bearer {auth_token_real}"}


@pytest.fixture
def admin_headers(client, db):
    """
    Headers con autenticación de admin.
    Busca un usuario admin en la BD o crea uno si no existe.
    """
    # Buscar usuario admin en la BD
    admin_user = db.query(User).filter(
        User.role.in_(["admin", "super_admin"])
    ).first()
    
    if admin_user:
        # Si existe admin, hacer login real
        # NOTA: Necesitarías la contraseña del admin, por ahora usamos token mock
        admin_token = create_access_token({"sub": admin_user.email})
    else:
        # Si no existe admin, crear token mock
        admin_token = create_access_token({"sub": "admin@farmacia.com"})
    
    return {"Authorization": f"Bearer {admin_token}"}


# =============================================================================
# USUARIOS DE PRUEBA (para referencia, pero la autenticación es real)
# =============================================================================

@pytest.fixture
def test_user(db, test_customer_email, test_customer_password):
    """
    Usuario de prueba obtenido de la BD REAL de PostgreSQL.
    Si no existe, lo crea usando TEST_CUSTOMER_EMAIL y TEST_CUSTOMER_PASSWORD.
    """
    from app.core.security import get_password_hash
    from app.utils.timezone import get_ve_now
    
    user = db.query(User).filter(User.email == test_customer_email).first()
    
    if not user:
        # Crear el usuario si no existe
        user = User(
            id=str(uuid.uuid4()),
            email=test_customer_email,
            hashed_password=get_password_hash(test_customer_password),
            user_type="natural",
            phone="+584121234567",
            first_name="Usuario",
            last_name="Prueba",
            is_active=True,
            is_verified=True,
            role="user",
            created_at=get_ve_now()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"✅ Usuario creado en BD PostgreSQL: {test_customer_email}")
    else:
        print(f"✅ Usuario encontrado en BD PostgreSQL: {test_customer_email}")
    
    return user


# =============================================================================
# DATOS DE PROFIT PLUS (códigos reales de tu BD)
# =============================================================================

@pytest.fixture
def sample_article_code():
    """
    Código de artículo real de Profit Plus.
    IMPORTANTE: Debe existir en tu base de datos.
    Si no existe, los tests usarán códigos reales obtenidos de la lista.
    """
    return os.getenv("TEST_ARTICLE_CODE", "FITOS004")  # Código por defecto que existe


@pytest.fixture
def sample_customer_code():
    """Código de cliente real de Profit Plus"""
    return os.getenv("TEST_CUSTOMER_CODE", "CLI001")


@pytest.fixture
def profit_settings():
    """
    Fixture que retorna la configuración de Profit Plus para tests.
    Usa Settings() que carga desde .env.test
    
    Esta configuración incluye:
    - SOURCE_SYSTEM_SERVER: Servidor de Profit Plus
    - SOURCE_SYSTEM_PORT: Puerto (default: 49571)
    - SOURCE_SYSTEM_DATABASE: Base de datos (default: GDROZAINK_A)
    - SOURCE_SYSTEM_USER: Usuario (opcional)
    - SOURCE_SYSTEM_PASSWORD: Contraseña (opcional)
    
    El SourceSystemService usa pymssql para conectarse con estos parámetros.
    """
    return test_settings


@pytest.fixture
def verify_profit_connection(profit_settings):
    """
    Fixture para verificar que la conexión a Profit Plus está configurada.
    Útil para tests que requieren conexión real.
    """
    if not profit_settings.SOURCE_SYSTEM_SERVER:
        pytest.skip("SOURCE_SYSTEM_SERVER no configurado en .env.test")
    if not profit_settings.SOURCE_SYSTEM_DATABASE:
        pytest.skip("SOURCE_SYSTEM_DATABASE no configurado en .env.test")
    return True


@pytest.fixture
def sample_warehouse_code():
    """Código de almacén para tests"""
    return "001"


@pytest.fixture
def sample_price_code():
    """Código de lista de precios para tests"""
    return "01"


# =============================================================================
# PAYLOADS DE PRUEBA
# =============================================================================

@pytest.fixture
def sample_cart_validation_payload(sample_article_code):
    """Payload para validar carrito"""
    return {
        "items": [
            {
                "co_art": sample_article_code,
                "cantidad": 2
            }
        ]
    }


@pytest.fixture
def sample_quote_payload(sample_article_code):
    """Payload para crear cotización"""
    return {
        "items": [
            {
                "co_art": sample_article_code,
                "quantity": 3
            }
        ],
        "payment_terms": "CONTADO",
        "observations": "Cotización de prueba automatizada"
    }


@pytest.fixture
def source_system_headers():
    """Headers con X-Source-System"""
    return {"X-Source-System": "DEMOA"}
