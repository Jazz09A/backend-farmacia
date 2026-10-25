"""Implementación del repositorio de imágenes (saArtImagen)."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from app.repositories.protocols import ImageRepositoryProtocol, _CursorProtocol

if TYPE_CHECKING:
    from app.services.source_system_service import SourceSystemService


class ImageRepository(ImageRepositoryProtocol):
    """Repositorio para operaciones sobre imágenes de artículos (saArtImagen)."""

    def __init__(self, source_service: SourceSystemService):
        self._source = source_service

    def _cursor(self) -> tuple[Any, _CursorProtocol]:
        conn = self._source.get_pooled_connection()
        cursor = conn.cursor()
        return conn, cursor

    def _release(self, conn: Any) -> None:
        self._source.return_connection(conn)

    def get_by_guid(self, image_guid: str) -> dict[str, Any] | None:
        """Obtiene datos binarios y metadatos de una imagen por GUID."""
        image_guid_clean = (image_guid or "").strip().upper().replace("{", "").replace("}", "")
        if not image_guid_clean:
            self._source.logger.warning("Se recibió un GUID vacío")
            return None

        self._source.logger.info(f"Buscando imagen con GUID: {image_guid_clean}")
        conn, cursor = self._cursor()
        try:
            cursor.execute(
                """
                SELECT
                    picture, imagen_des, tip, co_art
                FROM dbo.saArtImagen WITH (NOLOCK)
                WHERE rowguid = CAST(%s AS UNIQUEIDENTIFIER)
            """,
                (image_guid_clean,),
            )
            row = cursor.fetchone()

            if row:
                self._source.logger.info(
                    f"Imagen encontrada para GUID: {image_guid_clean}, artículo: {row.get('co_art')}"
                )
            else:
                self._source.logger.warning(f"No se encontró imagen con GUID: {image_guid_clean}")
            return row
        finally:
            cursor.close()
            self._release(conn)

    def _check_tip_exists(self, tip: str, article_code: str, cursor) -> bool:
        """Verifica si un código tip ya existe para un artículo."""
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM dbo.saArtImagen WITH (NOLOCK)
            WHERE co_art = %s AND tip = %s
        """,
            (article_code, tip),
        )
        result = cursor.fetchone()
        return result.get("count", 0) > 0 if result else False

    def _generate_unique_tip(self, article_code: str, cursor) -> str:
        """Genera código tip único (IMG001-IMG999)."""
        counter = 1
        max_attempts = 999
        while counter <= max_attempts:
            tip = f"IMG{counter:03d}"
            if not self._check_tip_exists(tip, article_code, cursor):
                return tip
            counter += 1
        raise ValueError(f"No se pudo generar un código tip único para el artículo {article_code}")

    def upload(
        self,
        article_code: str,
        image_bytes: bytes,
        description: str | None = None,
        tip: str | None = None,
        created_by: str = "API_USER",
    ) -> str:
        """Inserta una imagen y devuelve el rowguid generado."""
        # Validaciones de longitud ANTES de conectar a la BD
        article_code_clean = (article_code or "").strip()
        if not article_code_clean:
            raise ValueError("El código del artículo (co_art) no puede estar vacío")
        if len(article_code_clean) > 30:
            raise ValueError(
                f"El código del artículo '{article_code_clean}' tiene {len(article_code_clean)} caracteres, "
                f"pero el máximo permitido es 30."
            )

        # Truncar descripción si excede 60 chars
        description_clean = None
        if description:
            description_clean = description.strip()
            if len(description_clean) > 60:
                if "." in description_clean:
                    name_part, ext = description_clean.rsplit(".", 1)
                    max_name_len = 60 - len(ext) - 1
                    if max_name_len > 0:
                        description_clean = name_part[:max_name_len] + "." + ext
                    else:
                        description_clean = description_clean[:60]
                else:
                    description_clean = description_clean[:60]
                self._source.logger.warning(
                    f"El nombre de archivo fue truncado de '{description}' a '{description_clean}'"
                )

        # co_us_in: char(6) - usar código corto, no email
        created_by_clean = (created_by or "API").strip()
        if "@" in created_by_clean:
            created_by_clean = "API"
            self._source.logger.info(f"Se recibió un email '{created_by}', se usará el código 'API' para co_us_in")
        if len(created_by_clean) > 6:
            created_by_clean = created_by_clean[:6]
            self._source.logger.warning(f"El código de usuario fue truncado de '{created_by}' a '{created_by_clean}'")

        sucursal_code = "CCS"
        new_guid = str(uuid4())
        conn, cursor = self._cursor()
        try:
            if tip is None:
                tip = self._generate_unique_tip(article_code_clean, cursor)
                self._source.logger.info(f"Se generó automáticamente el código tip '{tip}' para {article_code_clean}")
            else:
                tip = tip.strip().upper()[:6]
                if tip == "PRINC":
                    self._source.logger.info(
                        f"Se usará el código tip 'PRINC' para la imagen principal de {article_code_clean}"
                    )
                if self._check_tip_exists(tip, article_code_clean, cursor):
                    raise ValueError(f"El código tip '{tip}' ya existe para el artículo {article_code_clean}.")

            cursor.execute(
                """
                INSERT INTO dbo.saArtImagen (
                    co_art, imagen_des, picture, tip,
                    co_us_in, fe_us_in, co_sucu_in,
                    co_us_mo, fe_us_mo, co_sucu_mo, rowguid
                )
                VALUES (%s, %s, %s, %s, %s, GETDATE(), %s, %s, GETDATE(), %s, %s)
            """,
                (
                    article_code_clean,
                    description_clean,
                    image_bytes,
                    tip,
                    created_by_clean,
                    sucursal_code,
                    created_by_clean,
                    sucursal_code,
                    new_guid,
                ),
            )
            conn.commit()
            return new_guid
        except ValueError:
            if conn:
                conn.rollback()
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            error_msg = str(e)
            if "truncated" in error_msg.lower() or "8152" in error_msg:
                raise ValueError(
                    f"Error de truncamiento de datos. "
                    f"co_art: '{article_code_clean}' ({len(article_code_clean)} chars), "
                    f"imagen_des: '{description_clean}' ({len(description_clean) if description_clean else 0} chars), "
                    f"co_us_in: '{created_by_clean}' ({len(created_by_clean)} chars), "
                    f"tip: '{tip}' ({len(tip) if tip else 0} chars). "
                    f"Error original: {error_msg}"
                )
            raise
        finally:
            cursor.close()
            self._release(conn)
