"""DI Container ligero — Factory functions + FastAPI Depends (nativo).

Proporciona inyección de dependencias sin librerías externas.
Compatible con pytest via app.dependency_overrides.
"""

from collections.abc import Generator
from contextlib import contextmanager

from fastapi import Depends

# Protocolos
from app.repositories.protocols import (
    ArticleRepositoryProtocol,
    CustomerRepositoryProtocol,
    DiscountRepositoryProtocol,
    HealthRepositoryProtocol,
    ImageRepositoryProtocol,
)

# Implementación concreta (orquestador con pool de conexiones)
from app.services.source_system_service import SourceSystemService

# =========================================================================
# Factories para repositorios
# =========================================================================

def get_source_system_service() -> SourceSystemService:
    """Retorna la instancia singleton de SourceSystemService.

    Esta función permite inyectar el servicio completo (con pool de conexiones)
    cuando se necesita acceso a métodos de pool/health que no están en los
    protocolos de dominio.
    """
    from app.services.source_system_service import source_system_service
    return source_system_service


def get_customer_repo() -> CustomerRepositoryProtocol:
    """Factory para CustomerRepositoryProtocol.

    SourceSystemService implementa todos los métodos del protocolo
    vía structural subtyping (typing.Protocol).
    """
    return get_source_system_service()  # type: ignore[return-value]


def get_article_repo() -> ArticleRepositoryProtocol:
    """Factory para ArticleRepositoryProtocol."""
    return get_source_system_service()  # type: ignore[return-value]


def get_discount_repo() -> DiscountRepositoryProtocol:
    """Factory para DiscountRepositoryProtocol."""
    return get_source_system_service()  # type: ignore[return-value]


def get_image_repo() -> ImageRepositoryProtocol:
    """Factory para ImageRepositoryProtocol."""
    return get_source_system_service()  # type: ignore[return-value]


def get_health_repo() -> HealthRepositoryProtocol:
    """Factory para HealthRepositoryProtocol."""
    return get_source_system_service()  # type: ignore[return-value]


# =========================================================================
# FastAPI Dependencies — usar directamente en endpoints
# =========================================================================

CustomerRepo = Depends(get_customer_repo)
ArticleRepo = Depends(get_article_repo)
DiscountRepo = Depends(get_discount_repo)
ImageRepo = Depends(get_image_repo)
HealthRepo = Depends(get_health_repo)
SourceSystemSvc = Depends(get_source_system_service)


# =========================================================================
# Context managers para uso fuera de FastAPI (scripts, tests, CLI)
# =========================================================================

@contextmanager
def customer_repo() -> Generator[CustomerRepositoryProtocol, None, None]:
    """Context manager para obtener repo de clientes fuera de FastAPI."""
    yield get_customer_repo()


@contextmanager
def article_repo() -> Generator[ArticleRepositoryProtocol, None, None]:
    """Context manager para obtener repo de artículos fuera de FastAPI."""
    yield get_article_repo()


@contextmanager
def discount_repo() -> Generator[DiscountRepositoryProtocol, None, None]:
    """Context manager para obtener repo de descuentos fuera de FastAPI."""
    yield get_discount_repo()


@contextmanager
def image_repo() -> Generator[ImageRepositoryProtocol, None, None]:
    """Context manager para obtener repo de imágenes fuera de FastAPI."""
    yield get_image_repo()


@contextmanager
def health_repo() -> Generator[HealthRepositoryProtocol, None, None]:
    """Context manager para obtener repo de health fuera de FastAPI."""
    yield get_health_repo()


@contextmanager
def source_system_svc() -> Generator[SourceSystemService, None, None]:
    """Context manager para obtener el servicio completo fuera de FastAPI."""
    yield get_source_system_service()


__all__ = [
    "ArticleRepo",
    "CustomerRepo",
    "DiscountRepo",
    "HealthRepo",
    "ImageRepo",
    "SourceSystemSvc",
    "article_repo",
    "customer_repo",
    "discount_repo",
    "get_article_repo",
    "get_customer_repo",
    "get_discount_repo",
    "get_health_repo",
    "get_image_repo",
    "get_source_system_service",
    "health_repo",
    "image_repo",
    "source_system_svc",
]