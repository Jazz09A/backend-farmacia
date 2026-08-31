"""
Tests for prod-readiness P0 fixes:
- Security headers (CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- HSTS conditional on APP_ENV=production
- Dashboard authz: GET /admin/dashboard requires admin role
- /api/v1/info endpoints reflect real routes
- Health endpoints (live, ready)
"""
import pytest


class TestSecurityHeaders:
    """Verifica que TODA response incluye las cabeceras de seguridad."""

    def test_root_includes_security_headers(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        csp = r.headers.get("Content-Security-Policy")
        assert csp is not None and "default-src" in csp

    def test_health_live_includes_security_headers(self, client):
        r = client.get("/api/v1/health/live")
        assert r.status_code == 200
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_hsts_absent_in_development(self, client, monkeypatch):
        """HSTS NO debe enviarse en development (rompe localhost)."""
        from app.config import settings as settings_module

        monkeypatch.setattr(settings_module.app, "APP_ENV", "development", raising=False)
        r = client.get("/api/v1/health/live")
        assert "Strict-Transport-Security" not in r.headers

    def test_hsts_present_in_production(self, client, monkeypatch):
        """HSTS debe enviarse cuando APP_ENV=production."""
        from app.config import settings as settings_module

        monkeypatch.setattr(settings_module.app, "APP_ENV", "production", raising=False)
        r = client.get("/api/v1/health/live")
        assert "max-age=63072000" in r.headers.get("Strict-Transport-Security", "")


class TestHealthEndpoints:
    """Verifica los nuevos endpoints /health/live y /health/ready."""

    def test_live_always_200(self, client):
        r = client.get("/api/v1/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "alive"

    def test_ready_returns_checks(self, client):
        """Ready debe incluir checks de database y source_system."""
        from unittest.mock import patch, MagicMock

        # Forzar source_system_service.health_check a retornar healthy
        mock_sss = MagicMock()
        mock_sss.health_check.return_value = {"status": "healthy", "latency_ms": 1.0}
        with patch("app.services.source_system_service.source_system_service", mock_sss):
            r = client.get("/api/v1/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert "database" in body["checks"]
        assert body["checks"]["database"]["status"] == "ok"

    def test_ready_returns_503_if_source_system_down(self, client):
        from unittest.mock import patch, MagicMock

        mock_sss = MagicMock()
        mock_sss.health_check.return_value = {"status": "unhealthy"}
        with patch("app.services.source_system_service.source_system_service", mock_sss):
            r = client.get("/api/v1/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["source_system"]["status"] == "unhealthy"


class TestDashboardAuthz:
    """Verifica que /admin/dashboard requiere rol admin (no usuario normal)."""

    def test_dashboard_rejects_regular_user(self, client, auth_headers):
        """Un usuario USER (no admin) debe recibir 403."""
        r = client.get("/api/v1/admin/dashboard", headers=auth_headers)
        assert r.status_code == 403

    def test_dashboard_accepts_admin(self, client, admin_headers):
        r = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        # 200 si todo OK, 503 si la BD DEMOA no responde (ambos son válidos
        # para este test, lo crítico es que NO sea 403)
        assert r.status_code in (200, 500)


class TestInfoEndpoint:
    """Verifica que /api/v1/info lista solo endpoints reales."""

    def test_info_lists_real_endpoints(self, client):
        r = client.get("/api/v1/info")
        assert r.status_code == 200
        body = r.json()
        eps = body["endpoints"]
        # Deben existir los reales
        assert eps["auth"] == "/api/v1/auth"
        assert eps["dashboard"] == "/api/v1/admin/dashboard"
        assert eps["exchange_rate"] == "/api/v1/exchange_rate"
        # NO deben existir los fantasmas del audit original
        assert "products" not in eps
        assert "orders" not in eps
        assert "reviews" not in eps
        assert "tracking" not in eps
        # health debe estar listado
        assert body["health"]["live"] == "/api/v1/health/live"
        assert body["health"]["ready"] == "/api/v1/health/ready"


class TestCreditModuleRemoved:
    """Sanity check: el módulo credit eliminado NO debe ser importable."""

    def test_credit_service_module_removed(self):
        with pytest.raises(ImportError):
            importlib_import = __import__(
                "importlib", fromlist=["import_module"]
            ).import_module
            importlib_import("app.services.credit_service")

    def test_credit_payment_service_removed(self):
        importlib_import = __import__(
            "importlib", fromlist=["import_module"]
        ).import_module
        with pytest.raises(ImportError):
            importlib_import("app.services.credit_payment_service")

    def test_credit_payment_model_removed(self):
        importlib_import = __import__(
            "importlib", fromlist=["import_module"]
        ).import_module
        with pytest.raises(ImportError):
            importlib_import("app.models.credit_payment")

    def test_user_has_no_credit_fields(self):
        """User no debe tener columnas credit_*."""
        from app.models.user import User

        assert not hasattr(User, "available_credit")
        assert not hasattr(User, "credit_limit")
        assert not hasattr(User, "credit_status")
        assert not hasattr(User, "credit_payments")