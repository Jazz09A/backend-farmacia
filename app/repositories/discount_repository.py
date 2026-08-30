"""Implementación del repositorio de descuentos (saDescArticulo, saTipoCliente, ofertas flash)."""
from decimal import Decimal
from typing import Any

from app.repositories.protocols import DiscountRepositoryProtocol, _CursorProtocol
from app.services.source_system_service import SourceSystemService


class DiscountRepository(DiscountRepositoryProtocol):
    """Repositorio para operaciones sobre descuentos de artículos (saDescArticulo)."""

    def __init__(self, source_service: SourceSystemService):
        self._source = source_service

    def _cursor(self) -> tuple[Any, _CursorProtocol]:
        conn = self._source.get_pooled_connection()
        cursor = conn.cursor()
        return conn, cursor

    def _release(self, conn: Any) -> None:
        self._source.return_connection(conn)

    def get_active_for_articles(
        self,
        article_codes: list[str],
        tip_cli: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Obtiene descuentos activos para múltiples artículos."""
        if not article_codes:
            return {}

        conn, cursor = self._cursor()
        try:
            # Normalizar códigos
            normalized = [code.upper().strip() for code in article_codes if code]
            if not normalized:
                return {}

            placeholders = ",".join(["%s"] * len(normalized))
            tip_filter = "AND RTRIM(tip_cli) = %s" if tip_cli else ""
            tip_param = (tip_cli,) if tip_cli else ()

            query = f"""
                SELECT co_art, co_desc, RTRIM(tip_cli) AS tip_cli,
                       campo1, campo2, campo3, campo4, campo5,
                       fecha_ini, fecha_fin, co_est, anulado
                FROM saDescArticulo WITH (NOLOCK)
                WHERE RTRIM(co_art) IN ({placeholders})
                  AND anulado = 0
                  AND (fecha_ini IS NULL OR fecha_ini <= GETDATE())
                  AND (fecha_fin IS NULL OR fecha_fin >= GETDATE())
                  {tip_filter}
            """
            params = tuple(normalized) + tip_param
            cursor.execute(query, params)
            rows = cursor.fetchall()

            result: dict[str, dict[str, Any]] = {}
            for row in rows:
                article_code = (row.get("co_art") or "").strip().upper()
                if article_code and article_code not in result:
                    result[article_code] = row
            return result
        finally:
            cursor.close()
            self._release(conn)

    def create(self, discount_data: dict[str, Any]) -> bool:
        conn, cursor = self._cursor()
        try:
            co_desc = discount_data.get("co_desc")
            if not co_desc:
                return False

            # Verificar si existe
            cursor.execute("SELECT co_desc FROM saDescArticulo WITH (NOLOCK) WHERE co_desc = %s", (co_desc,))
            exists = cursor.fetchone() is not None

            if exists:
                # UPDATE
                fields = []
                params = []
                for k, v in discount_data.items():
                    if k != "co_desc":
                        fields.append(f"{k} = %s")
                        params.append(v)
                if not fields:
                    return False
                params.append(co_desc)
                query = f"UPDATE saDescArticulo SET {', '.join(fields)} WHERE co_desc = %s"
                cursor.execute(query, tuple(params))
            else:
                # INSERT
                cols = list(discount_data.keys())
                placeholders = ",".join(["%s"] * len(cols))
                query = f"INSERT INTO saDescArticulo ({', '.join(cols)}) VALUES ({placeholders})"
                cursor.execute(query, tuple(discount_data.values()))

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            self._release(conn)

    def update_field(
        self,
        co_desc: str,
        data: dict[str, Any],
    ) -> bool:
        if not data:
            return False

        conn, cursor = self._cursor()
        try:
            fields = [f"{k} = %s" for k in data.keys()]
            params = list(data.values()) + [co_desc]
            query = f"UPDATE saDescArticulo SET {', '.join(fields)} WHERE co_desc = %s"
            cursor.execute(query, tuple(params))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            self._release(conn)

    def get_by_code(self, co_desc: str) -> dict[str, Any] | None:
        conn, cursor = self._cursor()
        try:
            cursor.execute("""
                SELECT co_desc, RTRIM(co_art) AS co_art, RTRIM(tip_cli) AS tip_cli,
                       campo1, campo2, campo3, campo4, campo5,
                       fecha_ini, fecha_fin, co_est, anulado
                FROM saDescArticulo WITH (NOLOCK)
                WHERE co_desc = %s
            """, (co_desc,))
            return cursor.fetchone()
        finally:
            cursor.close()
            self._release(conn)

    def list_discounts(
        self,
        co_art: str | None = None,
        tip_cli: str | None = None,
        only_active: bool = False,
        page: int = 1,
        limit: int = 50,
    ) -> dict[str, Any]:
        offset = (page - 1) * limit
        conn, cursor = self._cursor()
        try:
            filters = ["anulado = 0"]
            params: list[Any] = []

            if co_art:
                filters.append("RTRIM(co_art) = %s")
                params.append(co_art)
            if tip_cli:
                filters.append("RTRIM(tip_cli) = %s")
                params.append(tip_cli)
            if only_active:
                filters.append("(fecha_ini IS NULL OR fecha_ini <= GETDATE())")
                filters.append("(fecha_fin IS NULL OR fecha_fin >= GETDATE())")

            where = " AND ".join(filters) if filters else "1=1"

            # Count
            count_query = f"SELECT COUNT(*) AS total FROM saDescArticulo WITH (NOLOCK) WHERE {where}"
            cursor.execute(count_query, tuple(params))
            total_row = cursor.fetchone()
            total = total_row.get("total", 0) if total_row else 0

            # Data
            data_query = f"""
                SELECT co_desc, RTRIM(co_art) AS co_art, RTRIM(tip_cli) AS tip_cli,
                       campo1, campo2, campo3, campo4, campo5,
                       fecha_ini, fecha_fin, co_est, anulado
                FROM saDescArticulo WITH (NOLOCK)
                WHERE {where}
                ORDER BY co_desc
                OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """
            cursor.execute(data_query, tuple(params + [offset, limit]))
            items = cursor.fetchall()

            has_active = False
            has_expired = False
            from app.utils.timezone import get_ve_now
            now = get_ve_now()
            for item in items:
                ini = item.get("fecha_ini")
                fin = item.get("fecha_fin")
                active = (ini is None or ini <= now) and (fin is None or fin >= now)
                if active:
                    has_active = True
                else:
                    has_expired = True

            return {
                "items": items,
                "total": total,
                "page": page,
                "limit": limit,
                "has_active": has_active,
                "has_expired": has_expired,
            }
        finally:
            cursor.close()
            self._release(conn)

    def get_all_flash_offers(
        self,
        skip: int = 0,
        limit: int = 10,
        article_code: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        # Delegar al servicio existente por la complejidad de JOINs
        return self._source.get_flash_offers_paginated(skip=skip, limit=limit, article_code=article_code)

    def increment_usage(
        self,
        co_desc: str,
        quantity_used: int,
        field_name: str = "campo1",
        existing_cursor: _CursorProtocol | None = None,
    ) -> None:
        """Incrementa contador de uso (campoX) al aplicar descuento."""
        # Delegar al método existente que maneja transacciones y locks
        self._source.increment_discount_usage(
            co_desc=co_desc,
            quantity_used=quantity_used,
            field_name=field_name,
            existing_cursor=existing_cursor,
        )

    def validate_tip_cli(self, tip_cli: str) -> bool:
        conn, cursor = self._cursor()
        try:
            cursor.execute("SELECT 1 FROM saTipoCliente WITH (NOLOCK) WHERE RTRIM(tip_cli) = %s", (tip_cli,))
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            self._release(conn)

    def get_valid_tip_cli_codes(self) -> list[dict[str, Any]]:
        conn, cursor = self._cursor()
        try:
            cursor.execute("""
                SELECT RTRIM(tip_cli) AS tip_cli, RTRIM(des_tip) AS des_tip
                FROM saTipoCliente WITH (NOLOCK)
                ORDER BY tip_cli
            """)
            return cursor.fetchall()
        finally:
            cursor.close()
            self._release(conn)