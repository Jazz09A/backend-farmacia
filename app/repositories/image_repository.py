"""Implementación del repositorio de imágenes (saArtImagen)."""
from typing import Any

from app.repositories.protocols import ImageRepositoryProtocol, _CursorProtocol
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
        conn, cursor = self._cursor()
        try:
            query = """
                SELECT rowguid, co_art, tip, imagen_des, picture, fe_us_in
                FROM saArtImagen WITH (NOLOCK)
                WHERE rowguid = %s
            """
            cursor.execute(query, (image_guid,))
            return cursor.fetchone()
        finally:
            cursor.close()
            self._release(conn)

    def upload(
        self,
        article_code: str,
        image_bytes: bytes,
        description: str | None = None,
        tip: str | None = None,
        created_by: str = "API_USER",
    ) -> str:
        # Delegar al método existente que maneja la lógica compleja de GUID y tip único
        return self._source.upload_article_image(
            article_code=article_code,
            image_bytes=image_bytes,
            description=description,
            tip=tip,
            created_by=created_by,
        )