"""Implementación del repositorio de artículos (saArticulo, saArtPrecio, saStockAlmacen, saArtImagen)."""
from __future__ import annotations
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from app.repositories.protocols import ArticleRepositoryProtocol, _CursorProtocol

if TYPE_CHECKING:
    from app.services.source_system_service import SourceSystemService


class ArticleRepository(ArticleRepositoryProtocol):
    """Repositorio para operaciones sobre artículos en Profit plus."""

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
            header_query = """
                SELECT
                    a.co_art,
                    a.art_des,
                    a.ref,
                    a.co_lin,
                    a.co_subl,
                    a.co_cat,
                    cat.cat_des AS category_name,
                    a.tipo,
                    a.fecha_reg,
                    a.modelo
                FROM dbo.saArticulo a WITH (NOLOCK)
                LEFT JOIN dbo.saCatArticulo cat WITH (NOLOCK) ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
                WHERE a.co_art = %s AND a.anulado = 0
            """
            cursor.execute(header_query, (article_code,))
            header = cursor.fetchone()
            if not header:
                return None

            price_query = """
                SELECT
                    RTRIM(ap.co_precio) AS price_code,
                    tp.des_precio AS price_name,
                    ap.monto AS amount,
                    ap.co_mone AS currency,
                    ap.desde AS desde
                FROM dbo.saArtPrecio ap WITH (NOLOCK)
                LEFT JOIN dbo.saTipoPrecio tp WITH (NOLOCK) ON ap.co_precio = tp.co_precio
                WHERE ap.co_art = %s
                ORDER BY ap.desde DESC
            """
            cursor.execute(price_query, (article_code,))
            prices = cursor.fetchall() or []

            stock_query = """
                SELECT
                    RTRIM(sa.co_alma) AS warehouse_code,
                    al.des_alma AS warehouse_name,
                    sa.stock AS quantity
                FROM dbo.saStockAlmacen sa WITH (NOLOCK)
                LEFT JOIN dbo.saAlmacen al WITH (NOLOCK) ON sa.co_alma = al.co_alma
                WHERE sa.co_art = %s
                    AND sa.tipo = 'ACT'
            """
            cursor.execute(stock_query, (article_code,))
            stock = cursor.fetchall() or []

            images = self.get_images(article_code, connection=(conn, cursor))

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
        """Obtiene descuento aplicable para un artículo y cantidad.

        Delega a DiscountRepository para evitar duplicación.
        """
        from app.repositories import DiscountRepository
        discount_repo = DiscountRepository(self._source)
        return discount_repo.get_discount_for_article(
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
        """Busca artículos con filtros y paginación."""
        offset = (page - 1) * limit
        filters = ["a.anulado = 0"]
        params: list[Any] = [warehouse_code, price_code]

        if search:
            filters.append("(a.art_des LIKE %s OR a.co_art LIKE %s)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        if line_code:
            filters.append("RTRIM(a.co_lin) = %s")
            params.append(line_code)

        if category_code:
            filters.append("RTRIM(a.co_cat) = %s")
            params.append(category_code)

        if min_price is not None:
            filters.append("(ap.price IS NOT NULL AND ap.price >= %s)")
            params.append(Decimal(min_price))

        if max_price is not None:
            filters.append("(ap.price IS NOT NULL AND ap.price <= %s)")
            params.append(Decimal(max_price))

        if in_stock_only:
            filters.append("(ISNULL(stock_data.stock, 0) > 0)")

        where_clause = " AND ".join(filters)

        sort_mapping = {
            "art_des": "a.art_des ASC",
            "art_des_desc": "a.art_des DESC",
            "price_asc": "ap.price ASC",
            "price_desc": "ap.price DESC",
            "stock_asc": "stock_data.stock ASC",
            "stock_desc": "stock_data.stock DESC",
        }
        order_by = sort_mapping.get(sort_by, "a.art_des ASC")

        base_query = f"""
            FROM dbo.saArticulo a WITH (NOLOCK)
            LEFT JOIN dbo.saCatArticulo cat WITH (NOLOCK) ON RTRIM(a.co_cat) = RTRIM(cat.co_cat)
            OUTER APPLY (
                SELECT
                    RTRIM(sa.co_alma) AS co_alma,
                    SUM(sa.stock) AS stock
                FROM dbo.saStockAlmacen sa WITH (NOLOCK)
                WHERE sa.co_art = a.co_art
                    AND RTRIM(sa.co_alma) = %s
                    AND sa.tipo = 'ACT'
                GROUP BY sa.co_alma
            ) stock_data
            OUTER APPLY (
                SELECT TOP 1
                    ap.monto AS price,
                    ap.co_mone AS currency
                FROM dbo.saArtPrecio ap WITH (NOLOCK)
                WHERE ap.co_art = a.co_art
                    AND RTRIM(ap.co_precio) = %s
                ORDER BY ap.desde DESC
            ) ap
            OUTER APPLY (
                SELECT TOP 1 img.rowguid AS image_guid
                FROM dbo.saArtImagen img WITH (NOLOCK)
                WHERE img.co_art = a.co_art
                ORDER BY CASE WHEN img.tip = 'PRINC' THEN 0 ELSE 1 END, img.fe_us_in DESC
            ) img
            WHERE {where_clause}
        """

        data_query = f"""
            SELECT DISTINCT
                a.co_art,
                a.art_des,
                a.co_cat AS category_code,
                cat.cat_des AS category_name,
                ap.price,
                ap.currency,
                stock_data.stock AS stock,
                stock_data.co_alma AS warehouse_code,
                img.image_guid
            {base_query}
            ORDER BY {order_by}
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """

        count_query = f"""
            SELECT COUNT(DISTINCT a.co_art) AS total
            {base_query}
        """

        conn, cursor = self._cursor()
        try:
            cursor.execute(count_query, tuple(params))
            total_row = cursor.fetchone()
            total = total_row.get("total", 0) if total_row else 0

            cursor.execute(data_query, tuple(params + [offset, limit]))
            items = cursor.fetchall()

            return {
                "items": items or [],
                "total": total,
                "page": page,
                "limit": limit,
            }
        finally:
            cursor.close()
            self._release(conn)

    def get_images(
        self,
        article_code: str,
        connection: tuple[Any, _CursorProtocol] | None = None,
    ) -> list[dict[str, Any]]:
        if connection:
            _, cursor = connection
            cursor.execute("""
                SELECT
                    rowguid, imagen_des, tip, co_us_in, fe_us_in
                FROM dbo.saArtImagen WITH (NOLOCK)
                WHERE co_art = %s
                ORDER BY CASE WHEN tip = 'PRINC' THEN 0 ELSE 1 END, fe_us_in DESC
            """, (article_code,))
            return cursor.fetchall() or []
        else:
            conn, cursor = self._cursor()
            try:
                cursor.execute("""
                    SELECT
                        rowguid, imagen_des, tip, co_us_in, fe_us_in
                    FROM dbo.saArtImagen WITH (NOLOCK)
                    WHERE co_art = %s
                    ORDER BY CASE WHEN tip = 'PRINC' THEN 0 ELSE 1 END, fe_us_in DESC
                """, (article_code,))
                return cursor.fetchall() or []
            finally:
                cursor.close()
                self._release(conn)
