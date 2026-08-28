"""Tests de la jerarquía de excepciones y handlers globales."""
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    FarmaException,
    UserNotFoundException,
    ProductNotFoundException,
    OrderNotFoundException,
    InvalidCredentialsException,
    UserAlreadyExistsException,
    InsufficientStockException,
    PaymentProcessingException,
    CartEmptyException,
    EmailNotVerifiedException,
    FileUploadException,
    InvalidFileTypeException,
)
from main import app


pytestmark = pytest.mark.auth


@pytest.fixture
def exc_client():
    """Cliente sin la BD — solo necesitamos verificar la serialización de
    errores a través de un endpoint que no toque la BD."""
    with TestClient(app) as c:
        yield c


class TestExceptionHierarchy:
    def test_farma_exception_is_http_exception(self):
        exc = FarmaException(status_code=400, detail="test")
        assert exc.status_code == 400
        assert exc.detail == "test"

    @pytest.mark.parametrize(
        "exc_cls,expected_status",
        [
            (UserNotFoundException, 404),
            (ProductNotFoundException, 404),
            (OrderNotFoundException, 404),
            (InvalidCredentialsException, 401),
            (UserAlreadyExistsException, 400),
            (InsufficientStockException, 400),
            (PaymentProcessingException, 402),
            (CartEmptyException, 400),
            (EmailNotVerifiedException, 400),
            (FileUploadException, 400),
            (InvalidFileTypeException, 400),
        ],
    )
    def test_exception_status_codes(self, exc_cls, expected_status):
        exc = exc_cls()
        assert exc.status_code == expected_status

    def test_invalid_credentials_exception_has_www_authenticate(self):
        exc = InvalidCredentialsException()
        assert exc.headers == {"WWW-Authenticate": "Bearer"}


class TestExceptionHandlerResponses:
    def test_farma_exception_returns_json_envelope(self, exc_client):
        # /api/v1/auth/login con JSON inválido → 422
        r = exc_client.post("/api/v1/auth/login", json={})
        assert r.status_code in (400, 422)
        body = r.json()
        # El envelope debe tener al menos `detail` (validation tiene `errors` también)
        assert "detail" in body or "errors" in body

    def test_validation_error_returns_422(self, exc_client):
        r = exc_client.post("/api/v1/auth/login", json={"email": "not-an-email"})
        assert r.status_code == 422

    def test_internal_error_returns_generic_500(self, app, monkeypatch):
        # Forzar una excepción no manejada. Como authenticate_user es
        # staticmethod, parcheamos el método en la clase directamente.
        from app.services.auth_service import AuthService
        from fastapi.testclient import TestClient

        async def boom(*args, **kwargs):
            raise RuntimeError("simulated internal error")

        monkeypatch.setattr(AuthService, "authenticate_user", staticmethod(boom))
        # raise_server_exceptions=False para que el handler global los capture
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/api/v1/auth/login",
                json={"email": "x@x.com", "password": "Password1"},
            )
        assert r.status_code == 500
        # El cuerpo no debe filtrar detalles de la excepción
        body = r.json()
        assert body.get("success") is False
        assert "simulated internal error" not in body.get("detail", "")
