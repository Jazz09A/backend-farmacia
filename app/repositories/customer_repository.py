"""Implementación del repositorio de clientes (saCliente).

Encapsula todo el SQL crudo y lógica de negocio específica de clientes.
"""
from decimal import Decimal
from typing import Any

from app.repositories.protocols import CustomerRepositoryProtocol, _CursorProtocol
from app.services.source_system_service import SourceSystemService


class CustomerRepository(CustomerRepositoryProtocol):
    """Repositorio para operaciones sobre saCliente (Profit Plus / DEMOA)."""

    def __init__(self, source_service: SourceSystemService):
        self._source = source_service

    def _cursor(self) -> tuple[Any, _CursorProtocol]:
        """Obtiene conexión y cursor del servicio fuente."""
        conn = self._source.get_pooled_connection()
        cursor = conn.cursor()
        return conn, cursor

    def _release(self, conn: Any) -> None:
        self._source.return_connection(conn)

    def get_all(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        conn, cursor = self._cursor()
        try:
            filters = []
            params: list[Any] = []

            if not include_inactive:
                filters.append("inactivo = 0")
            if only_with_email:
                filters.append("(email IS NOT NULL AND email <> '' OR email_alterno IS NOT NULL AND email_alterno <> '')")
            if search:
                filters.append("(cli_des LIKE %s OR email LIKE %s OR co_cli LIKE %s)")
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param])

            where_clause = " AND ".join(filters) if filters else "1=1"

            if limit is not None:
                query = f"""
                    SELECT co_cli, cli_des, email, email_alterno, rif, telefonos,
                           direc1, direc2, inactivo, juridico, fecha_reg, tip_cli
                    FROM saCliente WITH (NOLOCK)
                    WHERE {where_clause}
                    ORDER BY cli_des
                    OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
                """
                params = [offset, limit] + params
            else:
                query = f"""
                    SELECT co_cli, cli_des, email, email_alterno, rif, telefonos,
                           direc1, direc2, inactivo, juridico, fecha_reg, tip_cli
                    FROM saCliente WITH (NOLOCK)
                    WHERE {where_clause}
                    ORDER BY cli_des
                """

            cursor.execute(query, tuple(params))
            return cursor.fetchall()
        finally:
            cursor.close()
            self._release(conn)

    def get_by_id(self, customer_code: str) -> dict[str, Any] | None:
        conn, cursor = self._cursor()
        try:
            query = """
                SELECT co_cli, cli_des, email, email_alterno, rif, telefonos,
                       direc1, direc2, inactivo, juridico, fecha_reg, tip_cli
                FROM saCliente WITH (NOLOCK)
                WHERE co_cli = %s
            """
            cursor.execute(query, (customer_code,))
            return cursor.fetchone()
        finally:
            cursor.close()
            self._release(conn)

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        conn, cursor = self._cursor()
        try:
            query = """
                SELECT co_cli, cli_des, email, email_alterno, rif, telefonos,
                       direc1, direc2, inactivo, juridico, fecha_reg, tip_cli
                FROM saCliente WITH (NOLOCK)
                WHERE email = %s OR email_alterno = %s
            """
            cursor.execute(query, (email, email))
            return cursor.fetchone()
        finally:
            cursor.close()
            self._release(conn)

    def get_addresses(self, customer_code: str) -> list[dict[str, Any]]:
        conn, cursor = self._cursor()
        try:
            query = """
                SELECT co_dir, direc1, direc2, direc3, direc4, co_pob, co_est,
                       co_zon, principal, tipo_dir
                FROM saDireccionEntrega WITH (NOLOCK)
                WHERE co_cli = %s
                ORDER BY principal DESC, co_dir
            """
            cursor.execute(query, (customer_code,))
            return cursor.fetchall()
        finally:
            cursor.close()
            self._release(conn)

    def get_profit_profile(self, email: str) -> dict[str, Any]:
        customer = self.get_by_email(email)
        if not customer:
            raise ValueError(f"No se encontró un cliente en Profit Plus asociado al email {email}")
        customer_code = customer.get("co_cli")
        if not customer_code:
            raise ValueError(f"El cliente asociado al email {email} no tiene código (co_cli) en Profit Plus")
        tip_cli = customer.get("tip_cli", "001")
        if not tip_cli:
            tip_cli = "001"
        return {
            "customer_code": customer_code,
            "tip_cli": tip_cli,
            "customer_name": customer.get("cli_des", ""),
        }

    def count(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        search: str | None = None,
    ) -> int:
        conn, cursor = self._cursor()
        try:
            filters = []
            params: list[Any] = []

            if not include_inactive:
                filters.append("inactivo = 0")
            if only_with_email:
                filters.append("(email IS NOT NULL AND email <> '' OR email_alterno IS NOT NULL AND email_alterno <> '')")
            if search:
                filters.append("(cli_des LIKE %s OR email LIKE %s OR co_cli LIKE %s)")
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param])

            where_clause = " AND ".join(filters) if filters else "1=1"
            query = f"SELECT COUNT(*) AS total FROM saCliente WITH (NOLOCK) WHERE {where_clause}"
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()
            return row.get("total", 0) if row else 0
        finally:
            cursor.close()
            self._release(conn)

    def build_user_code(self, customer_code: str) -> str:
        """Genera código válido de 6 caracteres para co_us_in/co_us_mo."""
        if customer_code and len(customer_code) <= 6:
            return customer_code.rjust(6, "0")
        return customer_code[:6] if customer_code else "000001"