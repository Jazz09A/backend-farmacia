"""Implementación del repositorio de clientes (saCliente).

Encapsula todo el SQL crudo y lógica de negocio específica de clientes.
"""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

from app.repositories.protocols import CustomerRepositoryProtocol, _CursorProtocol

if TYPE_CHECKING:
    from app.services.source_system_service import SourceSystemService


class CustomerRepository(CustomerRepositoryProtocol):
    """Repositorio para operaciones sobre saCliente (Profit Plus / DEMOA)."""

    def __init__(self, source_service: SourceSystemService):
        self._source = source_service

    def _cursor(self) -> tuple[Any, _CursorProtocol]:
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
            query = """
                SELECT
                    RTRIM(co_cli) AS customer_code,
                    RTRIM(cli_des) AS customer_name,
                    email,
                    email_alterno AS alternate_email,
                    rif,
                    telefonos AS phones,
                    direc1 AS address1,
                    direc2 AS address2,
                    RTRIM(tip_cli) AS tip_cli,
                    inactivo AS inactive,
                    juridico AS is_juridico,
                    fecha_reg AS registration_date
                FROM saCliente WITH (NOLOCK)
                WHERE 1=1
            """

            params = []

            if not include_inactive:
                query += " AND inactivo = 0"
            if only_with_email:
                query += " AND (email IS NOT NULL AND email != '' OR email_alterno IS NOT NULL AND email_alterno != '')"

            if search:
                search_pattern = f"%{search}%"
                query += " AND (LOWER(RTRIM(cli_des)) LIKE %s OR LOWER(RTRIM(co_cli)) LIKE %s)"
                params.extend([search_pattern.lower(), search_pattern.lower()])

            query += " ORDER BY cli_des"

            if limit:
                query += " OFFSET %s ROWS FETCH NEXT %s ROWS ONLY"
                params.extend([offset, limit])

            if params:
                cursor.execute(query, tuple(params))
            else:
                cursor.execute(query)
            customers = cursor.fetchall()
            return customers
        finally:
            cursor.close()
            self._release(conn)

    def count(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        search: str | None = None,
    ) -> int:
        conn, cursor = self._cursor()
        try:
            query = "SELECT COUNT(*) AS total FROM saCliente WITH (NOLOCK) WHERE 1=1"
            params = []

            if not include_inactive:
                query += " AND inactivo = 0"
            if only_with_email:
                query += " AND (email IS NOT NULL AND email != '' OR email_alterno IS NOT NULL AND email_alterno != '')"

            if search:
                search_pattern = f"%{search}%"
                query += " AND (LOWER(RTRIM(cli_des)) LIKE %s OR LOWER(RTRIM(co_cli)) LIKE %s)"
                params.extend([search_pattern.lower(), search_pattern.lower()])

            if params:
                cursor.execute(query, tuple(params))
            else:
                cursor.execute(query)
            result = cursor.fetchone()
            return result.get("total", 0) if result else 0
        finally:
            cursor.close()
            self._release(conn)

    def get_by_id(self, customer_code: str) -> dict[str, Any] | None:
        conn, cursor = self._cursor()
        try:
            query = """
                SELECT
                    RTRIM(co_cli) AS customer_code,
                    RTRIM(cli_des) AS customer_name,
                    email,
                    email_alterno AS alternate_email,
                    rif,
                    telefonos AS phones,
                    direc1 AS address1,
                    direc2 AS address2,
                    RTRIM(tip_cli) AS tip_cli,
                    inactivo AS inactive,
                    juridico AS is_juridico,
                    fecha_reg AS registration_date
                FROM saCliente WITH (NOLOCK)
                WHERE co_cli = %s
            """
            cursor.execute(query, (customer_code,))
            return cursor.fetchone()
        finally:
            cursor.close()
            self._release(conn)

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Obtiene cliente por email principal o alternativo.

        Usa cache de 5 minutos para evitar hammering del SQL Server
        en login/autoprovision.
        """
        from app.services.cache_service import cache_service

        cache_key = f"source:customer:by_email:{email.lower().strip()}"
        cached = cache_service.get_sync(cache_key)
        if cached is not None:
            return cached if cached != "__NULL__" else None
        conn, cursor = self._cursor()
        try:
            query = """
                SELECT
                    co_cli AS customer_code,
                    cli_des AS customer_name,
                    email,
                    email_alterno AS alternate_email,
                    rif,
                    telefonos AS phones,
                    direc1 AS address1,
                    direc2 AS address2,
                    inactivo AS inactive,
                    juridico AS is_juridico,
                    fecha_reg AS registration_date
                FROM saCliente WITH (NOLOCK)
                WHERE email = %s OR email_alterno = %s
            """
            cursor.execute(query, (email, email))
            customer = cursor.fetchone()
            cache_service.set_sync(cache_key, customer if customer else "__NULL__", ttl=300)
            return customer
        finally:
            cursor.close()
            self._release(conn)

    def get_addresses(self, customer_code: str) -> list[dict[str, Any]]:
        """Obtiene las direcciones de un cliente desde Profit plus (saCliente).

        Construye lista de hasta 3 direcciones (principal, entrega, secundaria)
        a partir de los campos direc1, dir_ent2, direc2.
        """
        conn, cursor = self._cursor()
        try:
            query = """
                SELECT
                    co_cli AS customer_code,
                    RTRIM(direc1) AS address1,
                    RTRIM(dir_ent2) AS delivery_address2,
                    RTRIM(direc2) AS address2,
                    RTRIM(ciudad) AS city,
                    RTRIM(zip) AS postal_code,
                    RTRIM(telefonos) AS phones,
                    RTRIM(cli_des) AS customer_name
                FROM dbo.saCliente WITH (NOLOCK)
                WHERE RTRIM(co_cli) = %s
            """
            cursor.execute(query, (customer_code.strip(),))
            result = cursor.fetchone()

            if not result:
                return []

            addresses = []

            # Dirección principal (direc1)
            if result.get("address1"):
                addresses.append(
                    {
                        "type": "principal",
                        "label": "Dirección Principal",
                        "address": result.get("address1", "").strip(),
                        "city": result.get("city", "").strip() if result.get("city") else None,
                        "postal_code": result.get("postal_code", "").strip() if result.get("postal_code") else None,
                        "phones": result.get("phones", "").strip() if result.get("phones") else None,
                        "customer_name": result.get("customer_name", "").strip()
                        if result.get("customer_name")
                        else None,
                    }
                )

            # Dirección de entrega 2 (dir_ent2)
            if result.get("delivery_address2"):
                addresses.append(
                    {
                        "type": "entrega",
                        "label": "Dirección de Entrega",
                        "address": result.get("delivery_address2", "").strip(),
                        "city": result.get("city", "").strip() if result.get("city") else None,
                        "postal_code": result.get("postal_code", "").strip() if result.get("postal_code") else None,
                        "phones": result.get("phones", "").strip() if result.get("phones") else None,
                        "customer_name": result.get("customer_name", "").strip()
                        if result.get("customer_name")
                        else None,
                    }
                )

            # Dirección secundaria (direc2)
            if result.get("address2"):
                addresses.append(
                    {
                        "type": "secundaria",
                        "label": "Dirección Secundaria",
                        "address": result.get("address2", "").strip(),
                        "city": result.get("city", "").strip() if result.get("city") else None,
                        "postal_code": result.get("postal_code", "").strip() if result.get("postal_code") else None,
                        "phones": result.get("phones", "").strip() if result.get("phones") else None,
                        "customer_name": result.get("customer_name", "").strip()
                        if result.get("customer_name")
                        else None,
                    }
                )

            return addresses
        finally:
            cursor.close()
            self._release(conn)

    def get_profit_profile(self, email: str) -> dict[str, Any]:
        """Obtiene perfil Profit del cliente (customer_code, tip_cli, customer_name)."""
        customer = self.get_by_email(email)
        if not customer:
            raise ValueError(f"No se encontró un cliente en Profit plus asociado al email {email}")
        customer_code = (customer.get("customer_code") or "").strip()
        if not customer_code:
            raise ValueError(f"El cliente asociado al email {email} no tiene código (co_cli) en Profit plus")
        tip_cli = (customer.get("tip_cli") or "").strip()
        if not tip_cli:
            tip_cli = "007"  # Default: cliente general
        return {
            "customer_code": customer_code,
            "tip_cli": tip_cli,
            "customer_name": customer.get("customer_name", ""),
        }

    def build_user_code(self, customer_code: str) -> str:
        """Genera código válido de 6 caracteres para co_us_in/co_us_mo."""
        if not customer_code:
            return "API"
        normalized = customer_code.strip().upper()
        if not normalized:
            return "API"
        return normalized[:6].ljust(6)

    def update_password(self, customer_code: str, hashed_password: str) -> bool:
        """Actualiza la contraseña de un cliente en saCliente."""
        conn, cursor = self._cursor()
        try:
            cursor.execute(
                "UPDATE saCliente SET password = %s WHERE co_cli = %s",
                (hashed_password, customer_code),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            self._release(conn)
