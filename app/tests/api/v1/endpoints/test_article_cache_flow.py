"""
Tests de integración del flujo de artículos cacheados (endpoint pesado).

Contrato que se verifica (por qué importa):
- El catálogo es el productor más pesado del cache: una segunda llamada
  idéntica DEBE servirse del cache sin re-consultar el SourceSystem
  (Profit). Si el cache pierde esa respuesta, cada request pagada es
  latencia extra en el endpoint más usado del comercio.
- Tras invalidar (como haría el panel o un cambio de imágenes), el
  cache debe refrescar SIN dejar de responder con el mismo contrato.
"""

import pytest

from app.services.cache_service import cache_service

CATALOG_PARAMS = {"page": 1, "limit": 10}


def catalog_payload() -> dict:
    """Shape REAL de respuesta del SourceSystem (mismo contrato de test_articles)."""
    return {
        "items": [
            {
                "co_art": "ART001",
                "art_des": "Test Article 1",
                "co_cat": "CAT001",
                "category_name": "Category 1",
                "price": "100.00",
                "currency": "VES",
                "stock": "10",
                "warehouse_code": "001",
            },
            {
                "co_art": "ART002",
                "art_des": "Test Article 2",
                "co_cat": "CAT002",
                "category_name": "Category 2",
                "price": "200.00",
                "currency": "VES",
                "stock": "5",
                "warehouse_code": "001",
            },
        ],
        "total": 2,
    }


@pytest.mark.integration
@pytest.mark.articles
@pytest.mark.cache
class TestArticleCacheFlow:
    def test_second_identical_catalog_call_is_served_from_cache(self, client, mock_profit_service, auth_headers):
        mock_profit_service.get_articles_catalog.return_value = catalog_payload()

        r1 = client.get("/api/v1/articles", params=CATALOG_PARAMS, headers=auth_headers)
        assert r1.status_code == 200
        consultas_primer_hit = mock_profit_service.get_articles_catalog.call_count
        assert consultas_primer_hit >= 1

        # 2ª llamada idéntica: misma clave de cache → hit, SIN re-consultar Profit.
        r2 = client.get("/api/v1/articles", params=CATALOG_PARAMS, headers=auth_headers)
        assert r2.status_code == 200
        assert mock_profit_service.get_articles_catalog.call_count == consultas_primer_hit
        assert r2.json()["total"] == r1.json()["total"]
        assert r2.json()["articles"][0]["co_art"] == "ART001"

        # 3ª llamada tras limpiar el cache: obligatoriamente vuelve a Profit.
        cache_service.clear_sync()
        r3 = client.get("/api/v1/articles", params=CATALOG_PARAMS, headers=auth_headers)
        assert r3.status_code == 200
        assert mock_profit_service.get_articles_catalog.call_count == consultas_primer_hit + 1

    def test_distinct_filters_produce_distinct_cache_keys(self, client, mock_profit_service, auth_headers):
        mock_profit_service.get_articles_catalog.return_value = catalog_payload()

        client.get("/api/v1/articles", params=CATALOG_PARAMS, headers=auth_headers)
        consultas = mock_profit_service.get_articles_catalog.call_count

        # Otros filtros = otra clave de cache → SÍ debe re-consultar.
        response = client.get(
            "/api/v1/articles",
            params={"page": 1, "limit": 10, "search": "Test"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert mock_profit_service.get_articles_catalog.call_count > consultas

    def test_invalidation_pattern_catalog_zoomed_by_admin(self, client, mock_profit_service, auth_headers):
        mock_profit_service.get_articles_catalog.return_value = catalog_payload()

        client.get("/api/v1/articles", params=CATALOG_PARAMS, headers=auth_headers)
        base = mock_profit_service.get_articles_catalog.call_count

        # El panel admin invalida el catálogo (la operación del endpoint evitado).
        cache_service.invalidate_pattern_sync("catalog:")

        client.get("/api/v1/articles", params=CATALOG_PARAMS, headers=auth_headers)
        assert mock_profit_service.get_articles_catalog.call_count == base + 1
