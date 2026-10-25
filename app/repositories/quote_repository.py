"""Implementación del repositorio de cotizaciones (saCotizacionCliente, saCotizacionClienteReng)."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

from app.repositories.protocols import _CursorProtocol

if TYPE_CHECKING:
    from app.services.source_system_service import SourceSystemService


class QuoteRepository:
    """Repositorio para operaciones sobre cotizaciones en Profit Plus."""

    def __init__(self, source_service: SourceSystemService):
        self._source = source_service

    def _cursor(self) -> tuple[Any, _CursorProtocol]:
        conn = self._source.get_pooled_connection()
        cursor = conn.cursor()
        return conn, cursor

    def _release(self, conn: Any) -> None:
        self._source.return_connection(conn)

    def list_for_user(
        self,
        co_cli: str,
        page: int = 1,
        limit: int = 10,
        status_filter: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Lista cotizaciones de un cliente con filtros y paginación."""
        offset = (page - 1) * limit
        conn, cursor = self._cursor()
        try:
            filters = ["co_cli = %s", "anulado = 0"]
            params: list[Any] = [co_cli]

            if status_filter:
                filters.append("status = %s")
                params.append(status_filter)

            if date_from:
                filters.append("fec_emis >= %s")
                params.append(date_from)

            if date_to:
                filters.append("fec_emis <= %s")
                params.append(date_to)

            where = " AND ".join(filters)

            # Count
            count_query = f"SELECT COUNT(*) AS total FROM saCotizacionCliente WITH (NOLOCK) WHERE {where}"
            cursor.execute(count_query, tuple(params))
            total_row = cursor.fetchone()
            total = total_row.get("total", 0) if total_row else 0

            # Data
            data_query = f"""
                SELECT doc_num, fec_emis, fec_venc, status, anulado,
                       total_neto, saldo, co_mone
                FROM saCotizacionCliente WITH (NOLOCK)
                WHERE {where}
                ORDER BY fec_emis DESC
                OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """
            cursor.execute(data_query, tuple(params + [offset, limit]))
            items = cursor.fetchall()

            return {
                "items": items,
                "total": total,
                "page": page,
                "limit": limit,
            }
        finally:
            cursor.close()
            self._release(conn)

    def get_by_doc_num(self, co_cli: str, doc_num: str) -> dict[str, Any] | None:
        conn, cursor = self._cursor()
        try:
            cursor.execute(
                """
                SELECT doc_num, fec_emis, fec_venc, status, anulado,
                       total_neto, saldo, co_mone, co_ven, co_cond, co_tran
                FROM saCotizacionCliente WITH (NOLOCK)
                WHERE co_cli = %s AND doc_num = %s AND anulado = 0
            """,
                (co_cli, doc_num),
            )
            return cursor.fetchone()
        finally:
            cursor.close()
            self._release(conn)

    def get_items(self, doc_num: str) -> list[dict[str, Any]]:
        conn, cursor = self._cursor()
        try:
            cursor.execute(
                """
                SELECT co_art, art_des, cantidad, precio, descuento, total_neto
                FROM saCotizacionClienteReng WITH (NOLOCK)
                WHERE doc_num = %s
                ORDER BY reng_num
            """,
                (doc_num,),
            )
            return cursor.fetchall()
        finally:
            cursor.close()
            self._release(conn)

    def get_discounts_for_quote(self, doc_num: str) -> list[dict[str, Any]]:
        conn, cursor = self._cursor()
        try:
            cursor.execute(
                """
                SELECT co_desc, co_art, cantidad, valor, porciento
                FROM saCotizacionClienteDesc WITH (NOLOCK)
                WHERE doc_num = %s
            """,
                (doc_num,),
            )
            return cursor.fetchall()
        finally:
            cursor.close()
            self._release(conn)
