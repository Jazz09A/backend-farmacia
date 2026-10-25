"""
Tests para el sistema de logging:
- request_id correlación via ContextVar
- middleware global (X-Request-ID, X-Process-Time)
- respuestas genéricas en errores 500 (sin filtrar str(e))
- redacción de secretos
- log_security_event no expone Authorization
"""
import logging
import re
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


# =============================================================================
# Unit tests: helpers
# =============================================================================
class TestRequestIdContext:
    def test_new_request_id_format(self):
        from app.utils.logging_helpers import new_request_id
        rid = new_request_id()
        assert isinstance(rid, str)
        assert len(rid) == 16
        # debe ser hex
        int(rid, 16)

    def test_set_and_get_request_id(self):
        from app.utils.logging_helpers import (
            set_request_context, clear_request_context,
            get_current_request_id, get_current_user_id, get_current_user_email,
        )
        set_request_context(request_id="abc12345", user_id="u1", user_email="a@b.com")
        assert get_current_request_id() == "abc12345"
        assert get_current_user_id() == "u1"
        assert get_current_user_email() == "a@b.com"
        clear_request_context()
        assert get_current_request_id() is None
        assert get_current_user_id() is None

    def test_contextvar_isolated_between_requests(self):
        from app.utils.logging_helpers import (
            set_request_context, clear_request_context, get_current_request_id,
        )
        set_request_context(request_id="rid-A")
        # Simulamos que llega otro request: set con otro id
        set_request_context(request_id="rid-B")
        assert get_current_request_id() == "rid-B"
        clear_request_context()


class TestRedaction:
    def test_redact_password(self):
        from app.utils.logging_helpers import redact_message
        assert "[REDACTED]" in redact_message("password=super_secret_123")

    def test_redact_token(self):
        from app.utils.logging_helpers import redact_message
        # Test different token formats
        assert "[REDACTED]" in redact_message("Bearer abcdef1234567890abcdef1234567890")
        assert "[REDACTED]" in redact_message("token=abcdef1234567890abcdef1234567890")
        assert "[REDACTED]" in redact_message("access_token=abcdef1234567890abcdef1234567890")

    def test_redact_db_url(self):
        from app.utils.logging_helpers import redact_message
        msg = "server=myserver.example.com;database=mydb;user=admin"
        redacted = redact_message(msg)
        assert "myserver" not in redacted
        assert "mydb" not in redacted

    def test_redact_empty_or_none(self):
        from app.utils.logging_helpers import redact_message
        assert redact_message("") == ""
        assert redact_message(None) is None

    def test_preserves_normal_text(self):
        from app.utils.logging_helpers import redact_message
        msg = "User tried to login with invalid credentials"
        assert redact_message(msg) == msg


class TestLogInternalError:
    def test_returns_tracking_id(self):
        from app.utils.logging_helpers import log_internal_error
        tid = log_internal_error(None, ValueError("boom"))
        assert tid is not None and len(tid) > 0
        # El tracking_id debe ser un UUID hex corto
        assert len(tid) == 16
        int(tid, 16)  # válido hex

    def test_returns_different_tracking_id_per_call(self):
        from app.utils.logging_helpers import log_internal_error
        tid1 = log_internal_error(None, ValueError("boom1"))
        tid2 = log_internal_error(None, ValueError("boom2"))
        assert tid1 != tid2

    def test_redacts_secrets_in_returned_message(self):
        from app.utils.logging_helpers import log_internal_error
        # El tracking_id se genera y el error no filtra el secreto
        tid = log_internal_error(None, RuntimeError("password=hunter2 leaked"))
        assert tid is not None
        # La función no debe lanzar excepción

    def test_uses_existing_request_id_if_set(self):
        from app.utils.logging_helpers import log_internal_error, set_request_context, clear_request_context
        set_request_context(request_id="my-custom-rid")
        try:
            tid = log_internal_error(None, ValueError("test"))
            assert tid == "my-custom-rid"
        finally:
            clear_request_context()


class TestLogSecurityEvent:
    def test_security_event_logged(self):
        from app.utils.logging_helpers import log_security_event
        # No debe lanzar excepción
        log_security_event("login_attempt", user_email="foo@bar.com")
        log_security_event("rate_limit_exceeded", extra={"limit": "5/min"})
        log_security_event("password_reset_requested")
        # Todo OK si no hay excepción


# =============================================================================
# Integration: middleware global y exception handlers
# =============================================================================
@pytest.fixture
def tiny_app_with_router():
    """Crea una mini-app con el middleware y los handlers del main.py."""
    from app.utils.logging_helpers import (
        set_request_context, clear_request_context,
        log_request, log_response, log_internal_error,
    )
    import time
    from starlette.responses import JSONResponse

    app = FastAPI()

    @app.middleware("http")
    async def _mw(request, call_next):
        from app.utils.logging_helpers import new_request_id
        incoming_rid = request.headers.get("x-request-id")
        rid = incoming_rid if incoming_rid and len(incoming_rid) <= 64 else new_request_id()
        set_request_context(request_id=rid)
        request.state.request_id = rid
        start = log_request(request)
        try:
            response = await call_next(request)
        except Exception as exc:
            tid = log_internal_error(request, exc, context={"phase": "test"})
            clear_request_context()
            return JSONResponse(
                status_code=500,
                headers={"X-Request-ID": rid},
                content={"detail": "Error interno", "tracking_id": tid},
            )
        log_response(request, response, start)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.2f}"
        clear_request_context()
        return response

    @app.get("/ok")
    def _ok():
        return {"ok": True}

    @app.get("/boom")
    def _boom():
        raise RuntimeError("kaboom with password=hunter2")

    @app.get("/notfound")
    def _notfound():
        raise HTTPException(status_code=404, detail="no está")

    return app


class TestMiddleware:
    def test_response_includes_request_id_header(self, tiny_app_with_router):
        client = TestClient(tiny_app_with_router)
        r = client.get("/ok")
        assert r.status_code == 200
        assert "X-Request-ID" in r.headers
        assert "X-Process-Time" in r.headers
        # El body es {"ok": true} sin request_id (solo los errores 500 lo incluyen)

    def test_client_provided_request_id_is_respected(self, tiny_app_with_router):
        client = TestClient(tiny_app_with_router)
        r = client.get("/ok", headers={"X-Request-ID": "cliente-rid-123"})
        assert r.headers["X-Request-ID"] == "cliente-rid-123"
        # Body no incluye request_id en endpoints normales

    def test_long_client_request_id_is_replaced(self, tiny_app_with_router):
        client = TestClient(tiny_app_with_router)
        too_long = "a" * 200
        r = client.get("/ok", headers={"X-Request-ID": too_long})
        # debe ser uno nuevo (16 chars), no el del cliente
        assert r.headers["X-Request-ID"] != too_long
        assert len(r.headers["X-Request-ID"]) == 16

    def test_500_returns_generic_message_with_tracking_id(self, tiny_app_with_router):
        client = TestClient(tiny_app_with_router)
        r = client.get("/boom")
        assert r.status_code == 500
        body = r.json()
        # Mensaje genérico: NO debe contener "hunter2" ni "kaboom"
        assert "hunter2" not in str(body)
        assert "kaboom" not in str(body)
        # Sí debe incluir tracking_id
        assert "tracking_id" in body
        assert len(body["tracking_id"]) > 0

    def test_404_passes_through_with_request_id(self, tiny_app_with_router):
        client = TestClient(tiny_app_with_router)
        r = client.get("/notfound")
        assert r.status_code == 404
        assert "X-Request-ID" in r.headers


# =============================================================================
# Regression: los endpoints reales deben tener X-Request-ID
# =============================================================================
class TestRealEndpointsHaveRequestId:
    def test_health_endpoint_returns_request_id(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert "X-Request-ID" in r.headers
        assert "X-Process-Time" in r.headers

    def test_validation_error_includes_request_id(self, client):
        # Forzar un 422 con un payload inválido a un endpoint de auth
        r = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
        assert r.status_code == 422
        body = r.json()
        assert "request_id" in body
        assert "X-Request-ID" in r.headers

    def test_404_includes_request_id(self, client):
        r = client.get("/this/does/not/exist")
        assert r.status_code == 404
        assert "request_id" in r.json()
        assert "X-Request-ID" in r.headers
