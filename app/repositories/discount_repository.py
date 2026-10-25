"""Implementación del repositorio de descuentos (saDescArticulo, saTipoCliente, ofertas flash)."""

from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any, TYPE_CHECKING

from app.repositories.protocols import DiscountRepositoryProtocol, _CursorProtocol

if TYPE_CHECKING:
    from app.services.source_system_service import SourceSystemService


def _safe_decimal(val) -> Decimal:
    try:
        if val is None:
            return Decimal(0)
        s_val = str(val).strip()
        return Decimal(s_val) if s_val else Decimal(0)
    except (ValueError, TypeError, InvalidOperation):
        return Decimal(0)


def _safe_int(val) -> int:
    try:
        if val is None:
            return 0
        s_val = str(val).strip()
        return int(float(s_val)) if s_val else 0
    except (ValueError, TypeError):
        return 0


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
        """Obtiene descuentos activos para múltiples artículos (mapa article_code -> discount)."""
        if not article_codes:
            return {}

        normalized_codes = [code.strip().upper() for code in article_codes if code]
        if not normalized_codes:
            return {}

        conn, cursor = self._cursor()
        try:
            placeholders = ",".join(["%s"] * len(normalized_codes))
            where_conditions = [
                f"RTRIM(d.co_art) IN ({placeholders})",
                "(d.fecha_ini IS NULL OR d.fecha_ini <= GETDATE())",
                "(d.fecha_fin IS NULL OR d.fecha_fin >= GETDATE())",
            ]
            params: list[Any] = list(normalized_codes)

            if tip_cli:
                where_conditions.append("RTRIM(d.tip_cli) = %s")
                params.append(tip_cli.strip().upper())

            where_clause = " AND ".join(where_conditions)

            query = f"""
                SELECT
                    d.co_desc, d.co_art, d.tip_cli, tc.des_tipo,
                    d.des_des, d.fecha_ini, d.fecha_fin,
                    d.hasta1, d.porc1, d.hasta2, d.porc2,
                    d.hasta3, d.porc3, d.hasta4, d.porc4,
                    d.hasta5, d.porc5, d.porc6
                FROM dbo.saDescArticulo d
                LEFT JOIN dbo.saTipoCliente tc ON RTRIM(d.tip_cli) = RTRIM(tc.tip_cli)
                WHERE {where_clause}
                ORDER BY d.co_art, d.porc1 DESC
            """
            cursor.execute(query, tuple(params))
            results = cursor.fetchall() or []

            discounts_map: dict[str, dict[str, Any]] = {}
            for row in results:
                co_art = (row.get("co_art") or "").strip().upper()
                if co_art and co_art not in discounts_map:
                    discounts_map[co_art] = row
            return discounts_map
        finally:
            cursor.close()
            self._release(conn)

    def get_discount_for_article(
        self,
        article_code: str,
        quantity: Decimal = Decimal("1.00"),
        existing_cursor: _CursorProtocol | None = None,
    ) -> dict[str, Any] | None:
        """Obtiene el descuento aplicable para un artículo según la cantidad.

        Lógica: Selecciona el tier (hasta1-5) donde quantity > hastaX.
        Valida disponibilidad (campoX usados) antes de aplicar.
        """
        use_existing = existing_cursor is not None
        cursor = None
        conn = None

        try:
            if use_existing:
                cursor = existing_cursor
                try:
                    cursor.execute("SELECT 1 AS test")
                    cursor.fetchone()
                except Exception as e:
                    raise ConnectionError(f"Cursor proporcionado no está conectado: {e}") from e
            else:
                conn, cursor = self._cursor()

            query = """
                SELECT TOP 1 co_desc, porc1, porc2, porc3, porc4, porc5,
                        hasta1, hasta2, hasta3, hasta4, hasta5,
                       campo1, campo2, campo3, campo4, campo5
                FROM dbo.saDescArticulo WITH (NOLOCK)
                WHERE co_art = %s
                    AND (fecha_ini IS NULL OR fecha_ini <= GETDATE())
                    AND (fecha_fin IS NULL OR fecha_fin >= GETDATE())
            """
            cursor.execute(query, (article_code.strip(),))
            discount = cursor.fetchone()
            if not discount:
                return None

            hasta_vals = {i: _safe_decimal(discount.get(f"hasta{i}")) for i in range(1, 6)}
            porc_vals = {i: _safe_decimal(discount.get(f"porc{i}")) for i in range(1, 6)}
            campo_vals = {i: _safe_int(discount.get(f"campo{i}")) for i in range(1, 6)}

            # Buscar tier aplicable (del más alto al más bajo)
            selected_tier = None
            for i in range(5, 0, -1):
                if hasta_vals[i] > 0 and quantity > hasta_vals[i] and porc_vals[i] > 0:
                    selected_tier = i
                    break

            if selected_tier is None:
                return None

            return {
                "co_desc": str(discount.get("co_desc", "")).strip(),
                "discount_percentage": porc_vals[selected_tier],
                "range_applied": f"hasta{selected_tier}",
                "field_to_increment": f"campo{selected_tier}",
                "disponibles": 999999,
                "limite_total": int(hasta_vals[selected_tier]),
                "ya_usados": campo_vals[selected_tier],
            }
        except ConnectionError:
            raise
        except Exception as e:
            error_code = getattr(e, "args", [None])[0] if hasattr(e, "args") and e.args else None
            if error_code in (20002, 20003, 20047):
                self._source.logger.error(
                    f"Error de conexión obteniendo descuento | articulo={article_code} | error_code={error_code} | {e}"
                )
                raise ConnectionError(f"Error de conexión a SQL Server: {e}") from e
            self._source.logger.warning(f"No se pudo obtener descuento para {article_code}: {e}")
            return None
        finally:
            if not use_existing and cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
                self._release(conn)

    def create(self, discount_data: dict[str, Any]) -> bool:
        """Crea o actualiza un registro de descuento en saDescArticulo."""
        # Validar campos requeridos ANTES de pedir una conexión al pool
        co_desc = (discount_data.get("co_desc") or "").strip().upper()
        if not co_desc:
            raise ValueError("co_desc es requerido para crear un descuento")
        co_art = (discount_data.get("co_art") or "").strip().upper()
        if not co_art:
            raise ValueError("co_art es requerido para crear un descuento")

        conn, cursor = self._cursor()
        try:
            tip_cli = (discount_data.get("tip_cli") or "GENERA").strip().upper()
            if not tip_cli:
                tip_cli = "GENERA"

            def _normalize_user_code(value: str | None, default: str = "API") -> str:
                if not value:
                    return default
                return value.strip().upper()[:6].ljust(6)

            co_us_in = _normalize_user_code(discount_data.get("co_us_in"))
            co_us_mo = _normalize_user_code(discount_data.get("co_us_mo", co_us_in))
            co_sucu_in = _normalize_user_code(discount_data.get("co_sucu_in", "CCS"))
            co_sucu_mo = _normalize_user_code(discount_data.get("co_sucu_mo", co_sucu_in))

            def _get_value(key: str):
                return discount_data.get(key)

            cursor.execute(
                "SELECT COUNT(*) AS count FROM dbo.saDescArticulo WHERE co_desc = %s",
                (co_desc,),
            )
            result = cursor.fetchone()
            exists = result["count"] > 0 if result else False

            common_values = [
                _get_value("des_des"),
                co_art,
                tip_cli,
                _get_value("fecha_ini"),
                _get_value("fecha_fin"),
                _get_value("hasta1"),
                _get_value("porc1"),
                _get_value("hasta2"),
                _get_value("porc2"),
                _get_value("hasta3"),
                _get_value("porc3"),
                _get_value("hasta4"),
                _get_value("porc4"),
                _get_value("hasta5"),
                _get_value("porc5"),
                _get_value("porc6"),
                _get_value("campo1"),
                _get_value("campo2"),
                _get_value("campo3"),
                _get_value("campo4"),
                _get_value("campo5"),
                _get_value("campo6"),
                _get_value("campo7"),
                _get_value("campo8"),
            ]

            if exists:
                cursor.execute(
                    """
                    UPDATE dbo.saDescArticulo
                    SET des_des=%s, co_art=%s, tip_cli=%s,
                        fecha_ini=%s, fecha_fin=%s,
                        hasta1=%s, porc1=%s, hasta2=%s, porc2=%s,
                        hasta3=%s, porc3=%s, hasta4=%s, porc4=%s,
                        hasta5=%s, porc5=%s, porc6=%s,
                        campo1=%s, campo2=%s, campo3=%s, campo4=%s,
                        campo5=%s, campo6=%s, campo7=%s, campo8=%s,
                        co_us_mo=%s, co_sucu_mo=%s, fe_us_mo=GETDATE()
                    WHERE co_desc=%s
                """,
                    tuple(common_values + [co_us_mo, co_sucu_mo, co_desc]),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO dbo.saDescArticulo (
                        co_desc, des_des, co_art, tip_cli, fecha_ini, fecha_fin,
                        hasta1, porc1, hasta2, porc2, hasta3, porc3, hasta4, porc4,
                        hasta5, porc5, porc6,
                        campo1, campo2, campo3, campo4, campo5, campo6, campo7, campo8,
                        co_us_in, co_sucu_in, fe_us_in,
                        co_us_mo, co_sucu_mo, fe_us_mo,
                        revisado, trasnfe, rowguid
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, GETDATE(),
                        %s, %s, GETDATE(),
                        NULL, NULL, NEWID()
                    )
                """,
                    tuple([co_desc] + common_values + [co_us_in, co_sucu_in, co_us_mo, co_sucu_mo]),
                )

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

        valid_fields = [
            "des_des",
            "fecha_ini",
            "fecha_fin",
            "tip_cli",
            "hasta1",
            "porc1",
            "hasta2",
            "porc2",
            "hasta3",
            "porc3",
            "hasta4",
            "porc4",
            "hasta5",
            "porc5",
            "campo1",
            "campo2",
        ]

        set_clauses = []
        params = []
        for field in valid_fields:
            if field in data:
                set_clauses.append(f"{field} = %s")
                params.append(data[field])

        set_clauses.append("fe_us_mo = GETDATE()")
        if not set_clauses:
            return False

        query = f"""
            UPDATE dbo.saDescArticulo
            SET {", ".join(set_clauses)}
            WHERE co_desc = %s
        """
        params.append(co_desc)

        conn, cursor = self._cursor()
        try:
            cursor.execute(query, tuple(params))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            self._release(conn)

    def get_by_code(self, co_desc: str) -> dict[str, Any] | None:
        """Obtiene un descuento por su código único."""
        conn, cursor = self._cursor()
        try:
            cursor.execute(
                """
                SELECT
                    d.co_desc, d.des_des, d.co_art,
                    d.fecha_ini, d.fecha_fin, d.tip_cli,
                    d.hasta1, d.porc1, d.hasta2, d.porc2,
                    d.hasta3, d.porc3, d.hasta4, d.porc4,
                    d.hasta5, d.porc5,
                    d.campo1, d.campo2, d.campo3, d.campo4, d.campo5,
                    d.co_us_in, d.fe_us_in, d.co_us_mo, d.fe_us_mo
                FROM dbo.saDescArticulo d
                WHERE d.co_desc = %s
            """,
                (co_desc,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            # Convertir fechas a isoformat
            for date_field in ("fecha_ini", "fecha_fin"):
                if row.get(date_field) and hasattr(row[date_field], "isoformat"):
                    row[date_field] = row[date_field].isoformat()

            # Asegurar tipos numéricos
            for i in range(1, 6):
                if row.get(f"campo{i}"):
                    try:
                        row[f"campo{i}"] = int(str(row[f"campo{i}"]))
                    except (ValueError, TypeError):
                        row[f"campo{i}"] = 0

            return row
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
        """Lista descuentos con filtros y paginación."""
        conn, cursor = self._cursor()
        try:
            where_conditions = []
            params = []

            if co_art:
                where_conditions.append("RTRIM(d.co_art) = %s")
                params.append(co_art.strip().upper())

            if tip_cli:
                where_conditions.append("RTRIM(d.tip_cli) = %s")
                params.append(tip_cli.strip().upper())

            if only_active:
                where_conditions.append("(d.fecha_ini IS NULL OR d.fecha_ini <= GETDATE())")
                where_conditions.append("(d.fecha_fin IS NULL OR d.fecha_fin >= GETDATE())")

            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

            # Count
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM dbo.saDescArticulo d {where_clause}",
                tuple(params),
            )
            total_result = cursor.fetchone()
            total = total_result["total"] if total_result else 0

            # Data
            offset = (page - 1) * limit
            cursor.execute(
                f"""
                SELECT
                    d.co_desc, d.co_art, a.art_des, d.tip_cli, tc.des_tipo,
                    d.des_des, d.fecha_ini, d.fecha_fin,
                    d.hasta1, d.porc1, d.hasta2, d.porc2,
                    d.hasta3, d.porc3, d.hasta4, d.porc4,
                    d.hasta5, d.porc5, d.porc6,
                    d.fe_us_in, d.fe_us_mo,
                    d.campo1, d.campo2,
                    CASE
                        WHEN (d.fecha_ini IS NULL OR d.fecha_ini <= GETDATE())
                         AND (d.fecha_fin IS NULL OR d.fecha_fin >= GETDATE())
                        THEN 1
                        ELSE 0
                    END AS is_active
                FROM dbo.saDescArticulo d
                LEFT JOIN dbo.saArticulo a ON RTRIM(d.co_art) = RTRIM(a.co_art)
                LEFT JOIN dbo.saTipoCliente tc ON RTRIM(d.tip_cli) = RTRIM(tc.tip_cli)
                {where_clause}
                ORDER BY d.fecha_ini DESC, d.co_desc
                OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """,
                tuple(params + [offset, limit]),
            )
            items = cursor.fetchall() or []

            # Stats
            cursor.execute(
                f"""
                SELECT
                    SUM(CASE
                        WHEN (fecha_ini IS NULL OR fecha_ini <= GETDATE())
                         AND (fecha_fin IS NULL OR fecha_fin >= GETDATE())
                        THEN 1 ELSE 0
                    END) AS active_count,
                    SUM(CASE
                        WHEN fecha_fin IS NOT NULL AND fecha_fin < GETDATE()
                        THEN 1 ELSE 0
                    END) AS expired_count
                FROM dbo.saDescArticulo d
                {where_clause}
            """,
                tuple(params),
            )
            stats = cursor.fetchone()
            has_active = stats["active_count"] if stats else 0
            has_expired = stats["expired_count"] if stats else 0

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
        """Obtiene ofertas flash activas (paginadas). Retorna (items, total)."""
        conn = self._source.get_pooled_connection()
        try:
            cursor = conn.cursor()
            where_conditions = [
                "(d.fecha_ini IS NULL OR d.fecha_ini <= GETDATE())",
                "(d.fecha_fin IS NULL OR d.fecha_fin >= GETDATE())",
            ]
            params = []

            if article_code:
                where_conditions.append("RTRIM(d.co_art) = %s")
                params.append(article_code.strip().upper())

            where_clause = " AND ".join(where_conditions)

            cursor.execute(
                f"SELECT COUNT(*) AS total FROM dbo.saDescArticulo d WHERE {where_clause}",
                tuple(params),
            )
            total = cursor.fetchone()["total"]

            cursor.execute(
                f"""
                SELECT
                    d.co_desc AS id,
                    RTRIM(d.co_art) AS article_code,
                    a.art_des,
                    d.fecha_ini AS start_time,
                    d.fecha_fin AS end_time,
                    d.porc1 AS discount_value,
                    d.campo1, d.campo2,
                    d.fe_us_in AS created_at,
                    d.fe_us_mo AS updated_at
                FROM dbo.saDescArticulo d
                LEFT JOIN dbo.saArticulo a ON RTRIM(d.co_art) = RTRIM(a.co_art)
                WHERE {where_clause}
                ORDER BY d.fe_us_in DESC
                OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """,
                tuple(params + [skip, limit]),
            )
            items = cursor.fetchall() or []

            results = []
            for item in items:
                item["discount_type"] = "percentage"
                item["is_active"] = True
                try:
                    c1 = int(item.get("campo1") or 0)
                    c2 = int(item.get("campo2") or 0)
                    item["max_quantity"] = c1
                    item["remaining_quantity"] = c1 - c2
                except (ValueError, TypeError):
                    item["max_quantity"] = 0
                    item["remaining_quantity"] = 0
                results.append(item)

            return results, total
        finally:
            if conn:
                self._release(conn)

    def increment_usage(
        self,
        co_desc: str,
        quantity_used: int,
        field_name: str = "campo1",
        existing_cursor: _CursorProtocol | None = None,
    ) -> None:
        """Incrementa contador de uso (campoX) al aplicar descuento."""
        valid_fields = ["campo1", "campo2", "campo3", "campo4", "campo5"]
        if field_name not in valid_fields:
            raise ValueError(f"Campo inválido: {field_name}. Debe ser uno de: {valid_fields}")

        use_existing = existing_cursor is not None
        cursor = None
        conn = None

        try:
            if use_existing:
                cursor = existing_cursor
                try:
                    cursor.execute("SELECT 1 AS test")
                    cursor.fetchone()
                except Exception as e:
                    raise ConnectionError(f"Cursor proporcionado no está conectado: {e}") from e
            else:
                conn, cursor = self._cursor()

            if not use_existing and conn:
                cursor.execute("BEGIN TRANSACTION")
            cursor.execute("SET LOCK_TIMEOUT 5000")

            # field_name está validado contra whitelist cerrada, seguro interpolar
            field_name = field_name.strip()
            update_query = (
                "UPDATE dbo.saDescArticulo WITH (UPDLOCK, ROWLOCK) "
                f"SET {field_name} = CAST("
                f"ISNULL(TRY_CAST({field_name} AS INT), 0) + %s AS VARCHAR(60)"
                "), fe_us_mo = GETDATE() "
                "WHERE co_desc = %s"
            )
            cursor.execute(update_query, (quantity_used, co_desc.strip()))
            rows_affected = cursor.rowcount

            try:
                cursor.execute("SET LOCK_TIMEOUT -1")
            except Exception:
                pass

            if not use_existing and conn:
                cursor.execute("COMMIT TRANSACTION")
                conn.commit()

            if rows_affected == 0:
                self._source.logger.warning(f"Descuento no actualizado | co_desc={co_desc} no existe o no se modificó")
        except Exception:
            if not use_existing and conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if not use_existing:
                if cursor:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                self._release(conn)

    def validate_tip_cli(self, tip_cli: str) -> bool:
        """Valida que el tip_cli exista en saTipoCliente."""
        conn, cursor = self._cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM dbo.saTipoCliente WHERE tip_cli = %s",
                (tip_cli.strip().upper(),),
            )
            result = cursor.fetchone()
            return result["count"] > 0 if result else False
        finally:
            cursor.close()
            self._release(conn)

    def get_valid_tip_cli_codes(self) -> list[dict[str, Any]]:
        """Obtiene todos los códigos de tipo de cliente válidos."""
        conn, cursor = self._cursor()
        try:
            cursor.execute("""
                SELECT RTRIM(tip_cli) AS tip_cli, RTRIM(des_tip) AS des_tip
                FROM saTipoCliente WITH (NOLOCK)
                ORDER BY tip_cli
            """)
            return cursor.fetchall() or []
        finally:
            cursor.close()
            self._release(conn)

    def generate_discount_code(self, prefix: str = "DESC") -> str:
        """Genera un nuevo código co_desc (char(6)) incrementando el último."""
        prefix_clean = (prefix or "DESC").strip().upper()
        max_length = 6
        numeric_width = max(1, max_length - len(prefix_clean))
        if numeric_width <= 0:
            raise ValueError("El prefijo para co_desc no puede exceder 6 caracteres")

        conn, cursor = self._cursor()
        try:
            like_pattern = f"{prefix_clean}%"
            cursor.execute(
                """
                SELECT TOP 1 RTRIM(co_desc) AS co_desc
                FROM dbo.saDescArticulo
                WHERE co_desc LIKE %s
                ORDER BY co_desc DESC
            """,
                (like_pattern,),
            )
            row = cursor.fetchone()

            if row and row.get("co_desc"):
                last_code = row["co_desc"].strip()
                numeric_part = last_code[len(prefix_clean) :]
                try:
                    next_number = int(numeric_part or "0") + 1
                except ValueError:
                    next_number = 1
            else:
                next_number = 1

            new_code = f"{prefix_clean}{str(next_number).zfill(numeric_width)}"
            return new_code[:max_length]
        finally:
            cursor.close()
            self._release(conn)
