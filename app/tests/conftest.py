"""
Configuración global de fixtures para tests.

Esta versión reemplaza el conftest previo que hacía login real contra la BD
y contra DEMOA (anti-patrón). Ahora los tests usan:

  * SQLite in-memory para la BD local (sin red, sin migraciones reales).
  * monkeypatch de `app.services.source_system_service.source_system_service`
    para evitar llamadas a Profit Plus / SQL Server.
  * fakes deterministas para SMTP / email.
  * un único `client` (TestClient) con override de `get_db`.

Las fixtures están diseñadas para que cualquier test pueda ejecutarse sin
acceder a servicios externos, sin requerir `.env.test` ni variables
adicionales.
"""
import os
import sys
import uuid
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

# Directorio raíz del proyecto (donde está main.py)
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Forzar modo test antes de importar nada del proyecto
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long-XXXX")
os.environ.setdefault("SMTP_PASSWORD", "test-smtp-password")
# Reducir ruido de logs durante los tests
os.environ.setdefault("CACHE_ENABLED", "False")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

# Cargar .env del proyecto (si existe) para variables no críticas,
# pero las variables de testing ya están fijadas arriba y tienen prioridad.
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=False)

# Importar modelos para que SQLAlchemy los registre en Base.metadata
from app.models import (  # noqa: E402
    User,
    Product,
    CartItem,
    Address,
    UserPreferences,
    Promotion,
    PromotionUsage,
    FlashOffer,
    PromotionalCode,
    DiscountType,
    Category,
    Brand,
    UserFavorite,
    CreditPayment,
    BlogPost,
    BlogCategory,
    BlogImage,
    ProductImage,
)
from app.config.database import Base, get_db  # noqa: E402
from app.config.settings import Settings  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.utils.timezone import get_ve_now  # noqa: E402
from app.schemas.role import UserRole  # noqa: E402


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

# Usamos StaticPool para que múltiples conexiones al in-memory DB compartan
# la misma BD (caso típico con TestClient + threadpool de FastAPI).
from sqlalchemy.pool import StaticPool

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Forzar FKs en SQLite (off por defecto)
@event.listens_for(engine, "connect")
def _enable_sqlite_fks(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _create_all_tables() -> None:
    # Importar modelos aquí garantiza que Base.metadata conoce todas las tablas
    Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Sesión de BD SQLite in-memory, transaccional.

    Cada test obtiene una BD limpia (todas las tablas creadas) y la sesión
    se cierra automáticamente al final. No se hace rollback explícito
    porque la BD vive solo durante la vida del engine, que es
    singleton pero se recrea con create_all para cada test (ver
    ``_create_all_tables``).
    """
    _create_all_tables()
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Limpiar todas las tablas para el siguiente test
        Base.metadata.drop_all(bind=engine)


# =============================================================================
# APP + CLIENT FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Limpia el rate-limiter de slowapi entre tests para evitar
    contaminación cruzada."""
    from app.core.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(scope="function")
def app(db):
    """FastAPI app con `get_db` overridden hacia la BD in-memory.

    Importante: ``main.py`` crea la app a nivel de módulo, lo cual
    inicializa singletons (CacheService, SourceSystemService, etc.).
    Para tests que tocan estos singletons, usar los fixtures
    ``mock_source_system_service`` y ``mock_email_service``.
    """
    # Importar dentro del fixture para que el override de DATABASE_URL
    # ya esté aplicado al import-time de los módulos.
    from main import app as fastapi_app

    def _override_get_db():
        try:
            yield db
        finally:
            # La sesión se cierra en el fixture `db`
            pass

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client(app) -> Generator[TestClient, None, None]:
    """TestClient de FastAPI con la BD in-memory."""
    with TestClient(app) as test_client:
        yield test_client


# =============================================================================
# MOCKS / FAKES
# =============================================================================

class FakeEmailService:
    """Sustituye a `app.services.email_service.email_service` durante los tests."""

    def __init__(self):
        self.sent_emails: list[dict] = []

    async def send_email(self, to_email: str, subject: str, template_name: str, context: dict):
        self.sent_emails.append(
            {
                "to": to_email,
                "subject": subject,
                "template": template_name,
                "context": context,
            }
        )
        return True

    async def send_password_reset_email(self, to_email: str, reset_link: str, user_name: str | None = None):
        self.sent_emails.append(
            {
                "to": to_email,
                "subject": "password_reset",
                "template": "password_reset",
                "context": {"reset_link": reset_link, "user_name": user_name},
            }
        )
        return True


class FakeSourceSystemService:
    """Sustituye a `app.services.source_system_service.source_system_service`.

    No abre conexiones reales. Los tests que necesiten valores específicos
    deben inyectarlos vía atributos del mock o usar `monkeypatch.setattr`
    sobre la instancia.
    """

    def __init__(self):
        self.customers: dict[str, dict] = {}
        self.articles: dict[str, dict] = {}
        self.health_status: dict = {"status": "healthy", "latency_ms": 1.0}

    def get_customer_by_email(self, email: str):
        return self.customers.get(email.lower())

    def get_article_detail(self, co_art: str):
        return self.articles.get(co_art)

    def health_check(self):
        return self.health_status

    # Stubs genéricos para métodos que no necesitamos cubrir en los
    # tests de auth/roles/exceptions/modelo. Si un test específico
    # los necesita, debe monkeypatchear el método concreto.
    def __getattr__(self, name):
        return MagicMock()


@pytest.fixture
def mock_email_service(monkeypatch):
    fake = FakeEmailService()
    # Reemplazar en todos los módulos que importaron la instancia singleton
    import app.services.email_service as email_module
    import app.services.auth_service as auth_module
    import app.services.source_system_user_creation_service as ssc_module

    monkeypatch.setattr(email_module, "email_service", fake)
    monkeypatch.setattr(auth_module, "email_service", fake)
    monkeypatch.setattr(ssc_module, "email_service", fake)
    return fake


@pytest.fixture
def mock_source_system_service(monkeypatch):
    fake = FakeSourceSystemService()
    import app.services.source_system_service as ss_module
    import app.services.auth_service as auth_module
    import app.services.quote_service as quote_module
    import app.services.dashboard_service as dashboard_module
    import app.services.user_service as user_module
    import app.services.article_service as article_module

    for mod in (ss_module, auth_module, quote_module, dashboard_module, user_module, article_module):
        if hasattr(mod, "source_system_service"):
            monkeypatch.setattr(mod, "source_system_service", fake)
    return fake


# =============================================================================
# USER FACTORIES
# =============================================================================

def _make_user(
    db: Session,
    *,
    email: str = "user@example.com",
    password: str = "Password1",
    role: str = UserRole.USER.value,
    is_active: bool = True,
    is_verified: bool = True,
    **kwargs,
) -> User:
    """Construye un usuario con defaults razonables para tests."""
    now = get_ve_now()
    base_kwargs = dict(
        id=str(uuid.uuid4()),
        email=email,
        hashed_password=get_password_hash(password),
        user_type=kwargs.pop("user_type", "natural"),
        phone=kwargs.pop("phone", "+584121234567"),
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        preferred_currency=kwargs.pop("preferred_currency", "VES"),
        is_active=is_active,
        is_verified=is_verified,
        role=role,
        created_at=now,
        updated_at=now,
    )
    base_kwargs.update(kwargs)
    user = User(**base_kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_factory(db):
    """Devuelve una factoría parametrizable de usuarios."""
    def _factory(**kwargs) -> User:
        return _make_user(db, **kwargs)
    return _factory


@pytest.fixture
def default_user(user_factory) -> User:
    return user_factory()


@pytest.fixture
def admin_user(user_factory) -> User:
    return user_factory(email="admin@example.com", role=UserRole.ADMIN.value)


@pytest.fixture
def super_admin_user(user_factory) -> User:
    return user_factory(email="superadmin@example.com", role=UserRole.SUPER_ADMIN.value)


@pytest.fixture
def manager_user(user_factory) -> User:
    return user_factory(email="manager@example.com", role=UserRole.MANAGER.value)


# =============================================================================
# AUTH HELPERS
# =============================================================================

@pytest.fixture
def make_token():
    """Devuelve una función que genera un JWT de acceso para el email dado."""
    from app.core.security import create_access_token

    def _make(email: str) -> str:
        return create_access_token({"sub": email})
    return _make


@pytest.fixture
def auth_headers(default_user, make_token) -> dict:
    return {"Authorization": f"Bearer {make_token(default_user.email)}"}


@pytest.fixture
def admin_headers(admin_user, make_token) -> dict:
    return {"Authorization": f"Bearer {make_token(admin_user.email)}"}


@pytest.fixture
def super_admin_headers(super_admin_user, make_token) -> dict:
    return {"Authorization": f"Bearer {make_token(super_admin_user.email)}"}


# =============================================================================
# SETTINGS
# =============================================================================

@pytest.fixture
def settings() -> Settings:
    return Settings()
