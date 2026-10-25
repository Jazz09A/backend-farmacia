"""Protocolos de repositorio para el sistema SourceSystem (Profit Plus).

Estos protocolos definen los contratos que deben cumplir las implementaciones
de repositorio. Usan typing.Protocol para structural subtyping, permitiendo
que cualquier clase que implemente los métodos requeridos sea compatible
sin necesidad de herencia explícita.

Diseño:
- Retornan Dict[str, Any] para filas SQL crudas (compatibilidad con pymssql.as_dict=True)
- Parámetros tipados con tipos concretos (Decimal, List[str], etc.)
- NO incluyen lógica de conexión/pool — eso queda en SourceSystemService (orquestador)
"""

from decimal import Decimal
from typing import Any, Protocol


class _CursorProtocol(Protocol):
    """Protocolo genérico para cursor de base de datos."""

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None: ...
    def fetchall(self) -> list[dict[str, Any]]: ...
    def fetchone(self) -> dict[str, Any] | None: ...
    def close(self) -> None: ...

    @property
    def rowcount(self) -> int: ...


class CustomerRepositoryProtocol(Protocol):
    """Protocolo para operaciones de clientes (saCliente)."""

    def get_all(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Obtiene lista paginada de clientes."""
        ...

    def get_by_id(self, customer_code: str) -> dict[str, Any] | None:
        """Obtiene un cliente por su código (co_cli)."""
        ...

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Obtiene un cliente por email principal o alternativo."""
        ...

    def get_addresses(self, customer_code: str) -> list[dict[str, Any]]:
        """Obtiene las direcciones de un cliente."""
        ...

    def get_profit_profile(self, email: str) -> dict[str, Any]:
        """Obtiene perfil Profit del cliente (customer_code, tip_cli, customer_name)."""
        ...

    def count(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        search: str | None = None,
    ) -> int:
        """Cuenta total de clientes (COUNT(*) en SQL)."""
        ...

    def build_user_code(self, customer_code: str) -> str:
        """Genera código válido de 6 caracteres para co_us_in/co_us_mo."""
        ...


class ArticleRepositoryProtocol(Protocol):
    """Protocolo para operaciones de artículos (saArticulo, saArtPrecio, saStockAlmacen)."""

    def get_detail(self, article_code: str) -> dict[str, Any] | None:
        """Obtiene detalle completo de un artículo (header, precios, stock, imágenes)."""
        ...

    def get_discount(
        self,
        article_code: str,
        quantity: Decimal = Decimal("1.00"),
        existing_cursor: _CursorProtocol | None = None,
    ) -> dict[str, Any] | None:
        """Obtiene descuento aplicable para un artículo y cantidad."""
        ...

    def search(
        self,
        page: int = 1,
        limit: int = 20,
        search: str | None = None,
        line_code: str | None = None,
        category_code: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        sort_by: str = "art_des",
        price_code: str = "01",
        warehouse_code: str = "001",
        in_stock_only: bool = False,
    ) -> dict[str, Any]:
        """Busca artículos con filtros y paginación. Retorna dict con items, total, page, limit."""
        ...

    def get_images(
        self,
        article_code: str,
        connection: tuple[Any, _CursorProtocol] | None = None,
    ) -> list[dict[str, Any]]:
        """Obtiene lista de imágenes asociadas a un artículo."""
        ...


class DiscountRepositoryProtocol(Protocol):
    """Protocolo para operaciones de descuentos de artículos (saDescArticulo)."""

    def get_active_for_articles(
        self,
        article_codes: list[str],
        tip_cli: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Obtiene descuentos activos para múltiples artículos (mapa article_code -> discount)."""
        ...

    def create(self, discount_data: dict[str, Any]) -> bool:
        """Crea o actualiza un descuento (INSERT o UPDATE según co_desc exista)."""
        ...

    def update_field(
        self,
        co_desc: str,
        data: dict[str, Any],
    ) -> bool:
        """Actualiza campos específicos de un descuento existente."""
        ...

    def get_by_code(self, co_desc: str) -> dict[str, Any] | None:
        """Obtiene un descuento por su código único."""
        ...

    def list_discounts(
        self,
        co_art: str | None = None,
        tip_cli: str | None = None,
        only_active: bool = False,
        page: int = 1,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Lista descuentos con filtros y paginación. Retorna items, total, page, limit, has_active, has_expired."""
        ...

    def get_all_flash_offers(
        self,
        skip: int = 0,
        limit: int = 10,
        article_code: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Obtiene ofertas flash activas (paginadas). Retorna (items, total)."""
        ...

    def increment_usage(
        self,
        co_desc: str,
        quantity_used: int,
        field_name: str = "campo1",
        existing_cursor: _CursorProtocol | None = None,
    ) -> None:
        """Incrementa contador de uso (campoX) al aplicar descuento."""
        ...

    def validate_tip_cli(self, tip_cli: str) -> bool:
        """Valida que el tip_cli exista en saTipoCliente."""
        ...

    def get_valid_tip_cli_codes(self) -> list[dict[str, Any]]:
        """Obtiene todos los códigos de tipo de cliente válidos."""
        ...


class ImageRepositoryProtocol(Protocol):
    """Protocolo para operaciones de imágenes de artículos (saArtImagen)."""

    def get_by_guid(self, image_guid: str) -> dict[str, Any] | None:
        """Obtiene datos binarios y metadatos de una imagen por GUID."""
        ...

    def upload(
        self,
        article_code: str,
        image_bytes: bytes,
        description: str | None = None,
        tip: str | None = None,
        created_by: str = "API_USER",
    ) -> str:
        """Inserta una imagen y devuelve el rowguid generado."""
        ...


class HealthRepositoryProtocol(Protocol):
    """Protocolo para health checks y métricas del pool de conexiones."""

    def health_check(self) -> dict[str, Any]:
        """Verifica salud del servicio y retorna status + pool stats."""
        ...

    def get_pool_stats(self) -> dict[str, Any]:
        """Obtiene estadísticas del pool de conexiones."""
        ...

    def dispose(self) -> None:
        """Cierra todas las conexiones del pool."""
        ...


__all__ = [
    "ArticleRepositoryProtocol",
    "CustomerRepositoryProtocol",
    "DiscountRepositoryProtocol",
    "HealthRepositoryProtocol",
    "ImageRepositoryProtocol",
]
