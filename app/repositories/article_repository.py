"""Implementación del repositorio de artículos (saArticulo, saArtPrecio, saStockAlmacen, saArtImagen)."""
from decimal import Decimal
from typing import Any

from app.repositories.protocols import ArticleRepositoryProtocol, _CursorProtocol
from app.services.source_system_service import SourceSystemService


class ArticleRepository(ArticleRepositoryProtocol):
    """Repositorio para operaciones sobre artículos en Profit Plus."""

    def __init__(self, source_service: SourceSystemService):
        self._source = source_service

    def _cursor(self) -> tuple[Any, _CursorProtocol]:
        conn = self._source.get_pooled_connection()
        cursor = conn.cursor()
        return conn, cursor

    def _release(self, conn: Any) -> None:
        self._source.return_connection(conn)

    def get_detail(self, article_code: str) -> dict[str, Any] | None:
        """Obtiene detalle completo: header, precios, stock, imágenes."""
        conn, cursor = self._cursor()
        try:
            # Header del artículo
            header_query = """
                SELECT co_art, art_des, ref, modelo, co_lin, co_subl, co_cat, tipo,
                       fecha_reg, anulado, co_und, co_imp
                FROM saArticulo WITH (NOLOCK)
                WHERE co_art = %s AND anulado = 0
            """
            cursor.execute(header_query, (article_code,))
            header = cursor.fetchone()
            if not header:
                return None

            # Precios
            prices_query = """
                SELECT co_precio, co_mone, monto, desde
                FROM saArtPrecio WITH (NOLOCK)
                WHERE co_art = %s
                ORDER BY co_precio
            """
            cursor.execute(prices_query, (article_code,))
            prices = cursor.fetchall()

            # Stock por almacén
            stock_query = """
                SELECT co_alma, stock
                FROM saStockAlmacen WITH (NOLOCK)
                WHERE co_art = %s AND tipo = 'ACT'
            """
            cursor.execute(stock_query, (article_code,))
            stock = cursor.fetchall()

            # Imágenes
            images_query = """
                SELECT rowguid, tip, imagen_des, fe_us_in
                FROM saArtImagen WITH (NOLOCK)
                WHERE co_art = %s
                ORDER BY CASE WHEN tip = 'PRINC' THEN 0 ELSE 1 END, fe_us_in DESC
            """
            cursor.execute(images_query, (article_code,))
            images = cursor.fetchall()

            return {
                "header": header,
                "prices": prices,
                "stock": stock,
                "images": images,
            }
        finally:
            cursor.close()
            self._release(conn)

    def get_discount(
        self,
        article_code: str,
        quantity: Decimal = Decimal("1.00"),
        existing_cursor: _CursorProtocol | None = None,
    ) -> dict[str, Any] | None:
        """Obtiene descuento aplicable para artículo y cantidad."""
        # Reutiliza la lógica existente en source_system_service
        # que ya maneja la lógica compleja de descuentos por volumen
        from app.services.source_system_service import source_system_service
        # Nota: esta implementación delega al servicio existente
        # En una refactorización completa, moveríamos toda la lógica aquí
        return source_system_service.get_article_discount(
            article_code=article_code,
            quantity=quantity,
            existing_cursor=existing_cursor,
        )

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
        """Busca artículos con filtros - delega al servicio existente."""
        offset = (page - 1) * limit
        # Delegar al método existente que ya tiene la lógica compleja con OUTER APPLY
        return self._source.get_articles_catalog(
            page=page,
            limit=limit,
            search=search,
            line_code=line_code,
            category_code=category_code,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            price_code=price_code,
            warehouse_code=warehouse_code,
            in_stock_only=in_stock_only,
        )

    def get_images(
        self,
        article_code: str,
        connection: tuple[Any, _CursorProtocol] | None = None,
    ) -> list[dict[str, Any]]:
        if connection:
            _, cursor = connection
            query = """
                SELECT rowguid, tip, imagen_des, fe_us_in
                FROM saArtImagen WITH (NOLOCK)
                WHERE co_art = %s
                ORDER BY CASE WHEN tip = 'PRINC' THEN 0 ELSE 1 END, fe_us_in DESC
            """
            cursor.execute(query, (article_code,))
            return cursor.fetchall()
        else:
            conn, cursor = self._cursor()
            try:
                query = """
                    SELECT rowguid, tip, imagen_des, fe_us_in
                    FROM saArtImagen WITH (NOLOCK)
                    WHERE co_art = %s
                    ORDER BY CASE WHEN tip = 'PRINC' THEN 0 ELSE 1 END, fe_us_in DESC
                """
                cursor.execute(query, (article_code,))
                return cursor.fetchall()
            finally:
                cursor.close()
                self._release(conn)