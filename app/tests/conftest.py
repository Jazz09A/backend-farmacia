"""
Configuración global de fixtures para tests con BD hermética (SQLite en memoria).

Los tests NO dependen de PostgreSQL ni de Profit Plus:
- La BD de usuarios se resuelve con SQLite en memoria (tablas creadas desde Base).
- Profit Plus (source_system_service / pymssql) se simula con fixtures de mock.
- El email se simula con mock_email_service.

IMPORTANTE: Este archivo carga .env.test ANTES de importar Settings
para asegurar que los tests usen la configuración correcta.
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
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
from main import app as main_app  # main.py está en la raíz
from app.config.database import Base as AppBase, get_db
from app.config.settings import Settings
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.utils.timezone import get_ve_now

# Registrar todos los modelos en Base.metadata antes de create_all
import app.models  # noqa: F401,E402


# Los modelos usan ARRAY de PostgreSQL, tipo que SQLite no soporta:
# solo para tests se cumple con TEXT.
@compiles(ARRAY, "sqlite")
def _pg_array_as_text(element, compiler, **kw):  # pragma: no cover
    return "TEXT"


# Instancia de Settings que usará las variables de .env.test
# Settings() lee automáticamente de os.getenv() y .env.test ya está cargado
test_settings = Settings()

SesionLocalTests = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)


def _make_test_engine():
    """Crea un engine SQLite en memoria con todas las tablas de Base creadas."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def db_session():
    """
    Sesión SQLite en memoria (hermética). Cada test opera dentro de una
    transacción que se revierte al finalizar, garantizando aislamiento total.
    """
    engine = _make_test_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = SesionLocalTests(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture(scope="function")
def db(db_session):
    """Alias hermético de db_session (BD en memoria)."""
    return db_session


@pytest.fixture(autouse=True)
def clean_cache_service():
    """Limpia el cache global entre tests (el singleton es compartido)."""
    import asyncio

    from app.services.cache_service import cache_service

    asyncio.run(cache_service.clear())
    yield
    asyncio.run(cache_service.clear())


# ─────────────────────────────────────────────────────────────────────────────
# Helper de creación de usuarios (lo importan los tests de endpoints)
# ─────────────────────────────────────────────────────────────────────────────


def _make_user(db, email, role="user", **overrides):
    """Crea un usuario de prueba en la sesión indicada y lo devuelve."""
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        hashed_password=get_password_hash("testpass123"),
        user_type="natural",
        phone="+584121234567",
        first_name="Usuario",
        last_name="Prueba",
        is_active=True,
        is_verified=True,
        role=role,
        created_at=get_ve_now(),
    )
    for field, value in overrides.items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def client(db):
    """
    Cliente de prueba FastAPI con BD hermética (SQLite en memoria).
    """

    def override_get_db():
        try:
            yield db
        finally:
            db.close()

    main_app.dependency_overrides[get_db] = override_get_db
    with TestClient(main_app) as test_client:
        yield test_client
    main_app.dependency_overrides.clear()


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
def auth_token_real(client, test_user):
    """
    Token JWT para el usuario de prueba (ya existe en la BD hermética gracias a test_user).
    """
    return create_access_token({"sub": test_user.email})


@pytest.fixture
def auth_headers(auth_token_real):
    """Headers con autenticación REAL obtenida del login"""
    return {"Authorization": f"Bearer {auth_token_real}"}


@pytest.fixture
def admin_headers(client, db):
    """
    Headers con autenticación de admin.

    Crea (o reutiliza) un usuario admin real en la BD hermética para que
    get_current_user pueda resolver el token.
    """
    # Buscar usuario admin en la BD
    admin_user = db.query(User).filter(User.role.in_(["admin", "super_admin"])).first()

    if admin_user is None:
        admin_created = _make_user(db, email="admin@farmacia.com", role="admin")
        admin_token = create_access_token({"sub": admin_created.email})
    else:
        admin_token = create_access_token({"sub": admin_user.email})

    return {"Authorization": f"Bearer {admin_token}"}


# =============================================================================
# USUARIOS DE PRUEBA (para referencia, pero la autenticación es real)
# =============================================================================


@pytest.fixture
def test_user(db, test_customer_email, test_customer_password):
    """
    Usuario de prueba creado en la BD hermética (SQLite en memoria).
    """
    from app.utils.timezone import get_ve_now

    user = db.query(User).filter(User.email == test_customer_email).first()

    if not user:
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
            created_at=get_ve_now(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

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
    return {"items": [{"co_art": sample_article_code, "cantidad": 2}]}


@pytest.fixture
def sample_quote_payload(sample_article_code):
    """Payload para crear cotización"""
    return {
        "items": [{"co_art": sample_article_code, "quantity": 3}],
        "payment_terms": "CONTADO",
        "observations": "Cotización de prueba automatizada",
    }


@pytest.fixture
def source_system_headers():
    """Headers con X-Source-System"""
    return {"X-Source-System": "DEMOA"}


# =============================================================================
# FIXTURES HERMÉTICAS (BD en memoria + mocks de servicios externos)
# =============================================================================


@pytest.fixture
def user_factory(db_session):
    """Fábrica de usuarios en la BD hermética.

    Acepta email opcional y role; devuelve el modelo User persistido.
    """

    def _factory(email=None, role="user", **overrides):
        return _make_user(
            db_session,
            email=email or f"user-{uuid.uuid4().hex[:10]}@test.local",
            role=role,
            **overrides,
        )

    return _factory


@pytest.fixture
def fake_pymssql():
    """Mock del módulo pymssql que SourceSystemService usaría para conectar."""
    from unittest.mock import MagicMock

    return MagicMock(name="fake_pymssql")


@pytest.fixture
def mock_source_system_service(monkeypatch):
    """MagicMock del servicio de Profit Plus inyectado en ArticleService.

    Los tests configuran métodos como get_articles_catalog / get_article_detail
    y el fixture restaura el original al terminar (via monkeypatch).
    """
    from unittest.mock import MagicMock
    from app.services.article_service import article_service

    mock = MagicMock(name="mock_source_system_service")
    # Defaults silenciosos para evitar llamadas sorpresa: sin descuentos,
    # catálogo vacío y detalle inexistente. Cada test sobreescribe lo que necesita.
    mock.get_active_discounts_for_articles.return_value = {}
    mock.get_articles_catalog.return_value = {"items": [], "total": 0}
    mock.get_article_detail.return_value = None
    monkeypatch.setattr(article_service, "_source_service", mock)
    return mock


@pytest.fixture
def mock_email_service(monkeypatch):
    """Reemplaza el singleton email_service en los módulos que lo importan."""
    from unittest.mock import MagicMock
    import importlib

    mock = MagicMock(name="mock_email_service")
    mock.sent_emails = []

    for module_name in (
        "app.api.v1.endpoints.quotes",
        "app.services.auth_service",
        "app.services.source_system_user_creation_service",
        "app.services.credit_payment_service",
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover
            continue
        if hasattr(module, "email_service"):
            monkeypatch.setattr(module, "email_service", mock)
    return mock


@pytest.fixture
def sample_customer():
    """Cliente hipotético de Profit Plus con el shape que devuelve source_system_service."""
    return {
        "customer_code": "CLI001",
        "email": "cliente@test.com",
        "nombre": "Cliente Test",
        "co_cli": "CLI001",
        "tip_cli": "001",
    }
