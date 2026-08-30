"""Implementación del repositorio de health checks y métricas del pool."""
from typing import Any

from app.repositories.protocols import HealthRepositoryProtocol
from app.services.source_system_service import SourceSystemService


class HealthRepository(HealthRepositoryProtocol):
    """Repositorio para health checks y métricas del pool de conexiones."""

    def __init__(self, source_service: SourceSystemService):
        self._source = source_service

    def health_check(self) -> dict[str, Any]:
        return self._source.health_check()

    def get_pool_stats(self) -> dict[str, Any]:
        return self._source.get_pool_stats()

    def dispose(self) -> None:
        self._source.dispose()