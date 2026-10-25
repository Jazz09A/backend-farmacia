"""Implementación del repositorio de health checks y métricas del pool."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

from app.repositories.protocols import HealthRepositoryProtocol

if TYPE_CHECKING:
    from app.services.source_system_service import SourceSystemService


class HealthRepository(HealthRepositoryProtocol):
    """Repositorio para health checks y métricas del pool de conexiones.

    Accede directamente al pool y a la conexión en lugar de delegar de vuelta
    a `source_system_service.health_check()` para evitar recursión infinita.
    """

    def __init__(self, source_service: "SourceSystemService"):
        self._source = source_service

    def health_check(self) -> dict[str, Any]:
        """Verifica salud del servicio y retorna métricas del pool."""
        try:
            with self._source.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 AS ping, GETDATE() AS server_time")
                result = cursor.fetchone()
                cursor.close()

            stats = self._source.get_pool_stats()
            return {
                "status": "healthy",
                "server_time": str(result.get("server_time")) if result else None,
                **stats,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                **self._source.get_pool_stats(),
            }

    def get_pool_stats(self) -> dict[str, Any]:
        return self._source.get_pool_stats()

    def dispose(self) -> None:
        self._source.dispose()
