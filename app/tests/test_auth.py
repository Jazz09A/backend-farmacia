"""Tests de autenticación: login, refresh, register, password reset.

Estos tests usan fixtures de `conftest.py`:
  * `db` → BD SQLite in-memory limpia por test
  * `client` → TestClient con `get_db` overridden
  * `user_factory` → crea usuarios parametrizados
  * `mock_source_system_service` / `mock_email_service` → fakes sin red
"""

import pytest


pytestmark = pytest.mark.auth


# =============================================================================
# LOGIN
# =============================================================================


class TestLogin:
    def test_login_ok_returns_tokens(self, client, user_factory, mock_source_system_service):
        user_factory(email="a@a.com", password="Password1")
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@a.com", "password": "Password1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    def test_login_invalid_password_returns_401(self, client, user_factory, mock_source_system_service):
        user_factory(email="a@a.com", password="Password1")
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@a.com", "password": "WrongPass1"},
        )
        assert response.status_code == 401
        # Mensaje genérico, no debe filtrar si el email existe
        body = response.json()
        assert "detail" in body

    def test_login_nonexistent_email_no_demoa_returns_401(self, client, mock_source_system_service):
        # sin usuario en BD y sin DEMOA hit → 401
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@nope.com", "password": "Password1"},
        )
        assert response.status_code == 401

    def test_login_inactive_user_returns_401(self, client, user_factory, mock_source_system_service):
        user_factory(email="a@a.com", password="Password1", is_active=False)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@a.com", "password": "Password1"},
        )
        assert response.status_code == 401

    def test_login_with_demoa_existing_user_no_local_anti_enumeration(
        self, client, mock_source_system_service, mock_email_service
    ):
        # Usuario existe en DEMOA pero no local → debe responder 401 con
        # el mismo mensaje genérico que un email totalmente inexistente,
        # para no permitir enumeración.
        mock_source_system_service.customers["a@a.com"] = {
            "customer_code": "DEMO-1",
            "email": "a@a.com",
        }
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@a.com", "password": "Password1"},
        )
        assert response.status_code == 401


# =============================================================================
# REFRESH
# =============================================================================


class TestRefresh:
    def test_refresh_ok(self, client, user_factory, mock_source_system_service):
        user_factory(email="a@a.com")
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@a.com", "password": "Password1"},
        )
        refresh = login_response.json()["refresh_token"]
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_with_access_token_returns_401(self, client, user_factory, mock_source_system_service):
        user_factory(email="a@a.com")
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@a.com", "password": "Password1"},
        )
        access = login_response.json()["access_token"]
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
        assert response.status_code == 401

    def test_refresh_with_garbage_token_returns_401(self, client):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})
        assert response.status_code == 401

    def test_refresh_with_empty_token_returns_400(self, client):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": ""})
        assert response.status_code in (400, 422)


# =============================================================================
# REGISTER
# =============================================================================


@pytest.fixture
def juridico_payload():
    return {
        "email": "nuevo@empresa.com",
        "password": "Password1",
        "phone": "+584121234567",
        "user_type": "juridico",
        "company_name": "Mi Empresa",
        "rif": "J-12345678-9",
        "registro_mercantil": "RM-001",
        "representante_legal_cedula": "V-12345678",
        "representante_legal_nombre": "Juan Pérez",
        "representantes_adicionales": None,
        "referencia_comercial_proveedor": "Proveedor X",
        "referencia_bancaria": "Banco Y",
        "direccion_establecimiento": "Calle 1, Caracas",
    }


class TestRegister:
    def test_register_ok(self, client, juridico_payload, mock_source_system_service, mock_email_service):
        response = client.post("/api/v1/auth/register", json=juridico_payload)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == juridico_payload["email"]
        # Email de verificación enviado
        assert len(mock_email_service.sent_emails) == 1

    def test_register_duplicate_email_returns_409_or_400(
        self, client, juridico_payload, user_factory, mock_source_system_service
    ):
        user_factory(email=juridico_payload["email"])
        response = client.post("/api/v1/auth/register", json=juridico_payload)
        # El endpoint convierte HTTPException 400; en cualquier caso
        # NO debe crear el usuario.
        assert response.status_code in (400, 409)
        assert response.json().get("success") is False or "detail" in response.json()

    def test_register_weak_password_returns_422(self, client, juridico_payload, mock_source_system_service):
        juridico_payload["password"] = "short"
        response = client.post("/api/v1/auth/register", json=juridico_payload)
        assert response.status_code == 422


# =============================================================================
# PASSWORD RESET
# =============================================================================


class TestPasswordReset:
    def test_forgot_password_existing_user_sends_email(
        self, client, user_factory, mock_source_system_service, mock_email_service
    ):
        user_factory(email="a@a.com")
        response = client.post("/api/v1/auth/forgot-password", json={"email": "a@a.com"})
        # No debe enumerar
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert len(mock_email_service.sent_emails) >= 1

    def test_forgot_password_nonexistent_email_does_not_enumerate(
        self, client, mock_source_system_service, mock_email_service
    ):
        response = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@nope.com"})
        assert response.status_code == 200
        assert response.json()["success"] is True
        # No debe enviar email cuando el usuario no existe
        assert len(mock_email_service.sent_emails) == 0

    def test_reset_password_with_garbage_token_returns_400(self, client, mock_source_system_service):
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "garbage", "new_password": "Password1"},
        )
        # 422 por validación de Pydantic (sin confirm_password) o 400/404
        # por token inválido. Lo importante es que NO sea 200.
        assert response.status_code in (400, 404, 422)


# =============================================================================
# CHANGE PASSWORD
# =============================================================================


class TestChangePassword:
    def test_change_password_uses_body_not_query(self, client, default_user, auth_headers, mock_source_system_service):
        # Si se pasa por query string, FastAPI no acepta los params y
        # el body está vacío, por lo que se rechaza con 422 (Pydantic)
        # o se devuelve 403 (token no se envía correctamente). Lo
        # importante es que NO se cambie la contraseña.
        response = client.post(
            "/api/v1/auth/change-password?current_password=Password1&new_password=Password2",
        )
        assert response.status_code in (401, 403, 422)
        # Verificar que el body real sí funciona (sigue siendo POST con JSON)
        response_body = client.post(
            "/api/v1/auth/change-password",
            headers=auth_headers,
            json={"current_password": "Password1", "new_password": "NewPassword2"},
        )
        assert response_body.status_code == 200

    def test_change_password_ok(self, client, default_user, auth_headers, mock_source_system_service):
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth_headers,
            json={"current_password": "Password1", "new_password": "NewPassword2"},
        )
        assert response.status_code == 200

    def test_change_password_wrong_current_returns_401(
        self, client, default_user, auth_headers, mock_source_system_service
    ):
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth_headers,
            json={"current_password": "WrongPass1", "new_password": "NewPassword2"},
        )
        assert response.status_code == 401


# =============================================================================
# ENUMERACIÓN
# =============================================================================


class TestAntiEnumeration:
    def test_get_email_verification_returns_same_message_for_existing_and_nonexistent(
        self, client, user_factory, mock_source_system_service
    ):
        user_factory(email="exists@a.com")
        r1 = client.get("/api/v1/auth/get-email-verification/exists@a.com")
        r2 = client.get("/api/v1/auth/get-email-verification/ghost@nope.com")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Mismo `message` y `success` para que un atacante no pueda
        # distinguir entre emails registrados y no.
        assert r1.json() == r2.json()
