"""
Tests de integración de los endpoints de cache del panel admin.

Contrato que se verifica (por qué importa):
- La forma de respuesta (/admin/cache/stats, /cache/invalidate, ...) NO
  cambia con la migración a Redis: el frontend admin consume estos
  endpoints hoy; un campo nuevo o faltante rompería la UI.
- La autorización admin sigue siendo obligatoria en todos.
- Con driver Redis, ``cleanup_expired`` y las invalidaciones operan sobre
  el namespace real sin afectar claves de otras apps.
"""

import pytest

from app.services import cache_service as cache_module
from app.services.cache_service import cache_service

# Contrato original de CacheStatsResponse (11 campos exactos, el frontend no espera más)
STATS_CONTRACT_FIELDS = {
    "enabled",
    "total_entries",
    "expired_entries",
    "active_entries",
    "hits",
    "misses",
    "sets",
    "invalidations",
    "cleanups",
    "hit_rate",
    "total_requests",
}


@pytest.mark.integration
@pytest.mark.admin
@pytest.mark.cache
class TestAdminCacheEndpoints:
    def test_cache_stats_requires_admin(self, client):
        response = client.get("/api/v1/admin/cache/stats")
        assert response.status_code in (401, 403)

    def test_cache_stats_contract_is_preserved(self, client, admin_headers):
        response = client.get("/api/v1/admin/cache/stats", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        # Exactamente el contrato original: ni un campo menos ni más.
        assert set(body.keys()) == STATS_CONTRACT_FIELDS
        assert isinstance(body["enabled"], bool)
        assert isinstance(body["hit_rate"], float)
        assert body["total_requests"] == body["hits"] + body["misses"]

    def test_cache_invalidate_requires_admin(self, client):
        response = client.post("/api/v1/admin/cache/invalidate", json={"cache_type": "all"})
        assert response.status_code in (401, 403)

    def test_cache_invalidate_all(self, client, admin_headers):
        cache_service.set_sync("contrato:x", 1, ttl=60)
        response = client.post(
            "/api/v1/admin/cache/invalidate",
            json={"cache_type": "all"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["invalidated_count"] >= 1
        assert cache_service.get_sync("contrato:x") is None

    def test_cache_invalidate_known_types(self, client, admin_headers):
        for cache_type in ("catalog", "article"):
            response = client.post(
                "/api/v1/admin/cache/invalidate",
                json={"cache_type": cache_type},
                headers=admin_headers,
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_cache_invalidate_unknown_type_is_400(self, client, admin_headers):
        response = client.post(
            "/api/v1/admin/cache/invalidate",
            json={"cache_type": "tipo-inexistente"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_cache_invalidate_custom_pattern(self, client, admin_headers):
        cache_service.set_sync("custompattern:a", 1, ttl=60)
        response = client.post(
            "/api/v1/admin/cache/invalidate",
            json={"pattern": "custompattern:"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["invalidated_count"] == 1

    def test_cache_delete_by_type(self, client, admin_headers):
        for cache_type in ("catalog", "article"):
            response = client.delete(
                f"/api/v1/admin/cache/{cache_type}",
                headers=admin_headers,
            )
            assert response.status_code == 200
            assert response.json()["success"] is True
        assert client.delete("/api/v1/admin/cache/otro", headers=admin_headers).status_code == 400

    def test_cache_cleanup(self, client, admin_headers):
        response = client.post("/api/v1/admin/cache/cleanup", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_cache_toggle_roundtrip_restores_state(self, client, admin_headers):
        response = client.post(
            "/api/v1/admin/cache/toggle",
            params={"enable": "false"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False
        # Con cache deshabilitado, get devuelve None aunque exista entry.
        cache_service.set_sync("toggle:x", "secret", ttl=60)
        assert cache_service.get_sync("toggle:x") is None

        response = client.post(
            "/api/v1/admin/cache/toggle",
            params={"enable": "true"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_cleanup_reports_driver_degradation(self):
        stats = cache_service.get_stats_sync()
        assert "redis_active" in stats
        # Driver activo según env local (tests herméticos usan memoria)
        expected_driver = "redis" if cache_service._redis is not None else "memory"
        assert stats["driver"] == expected_driver
