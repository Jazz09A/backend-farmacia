"""
Servicio de Cloudinary para gestión de imágenes en la nube.

Proporciona funcionalidades para:
- Subir imágenes (archivos, bytes, URLs)
- Eliminar imágenes
- Transformar imágenes (redimensionar, optimizar)
- Obtener información de imágenes
"""

from enum import Enum
from typing import Any, Optional

import cloudinary
import cloudinary.api
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from fastapi import HTTPException, UploadFile, status

from app.config.logging_config import get_logger
from app.config.settings import Settings

logger = get_logger("cloudinary_service")
settings = Settings()


class ImageFormat(str, Enum):
    """Formatos de imagen soportados."""

    AUTO = "auto"
    WEBP = "webp"
    PNG = "png"
    JPG = "jpg"
    AVIF = "avif"


class CloudinaryFolder(str, Enum):
    """Carpetas predefinidas en Cloudinary."""

    PRODUCTS = "products"
    BLOG = "farmaplus/blog"
    USERS = "farmaplus/users"
    CATEGORIES = "farmaplus/categories"
    PROMOTIONS = "farmaplus/promotions"
    GENERAL = "farmaplus/general"


class CloudinaryService:
    """
    Servicio para gestionar imágenes en Cloudinary.

    Uso:
        cloudinary_service = CloudinaryService()
        result = await cloudinary_service.upload_image(file, folder="products")
    """

    _instance: Optional["CloudinaryService"] = None
    _configured: bool = False

    def __new__(cls) -> "CloudinaryService":
        """Implementa patrón Singleton para reutilizar la configuración."""
        if CloudinaryService._instance is None:
            CloudinaryService._instance = super().__new__(cls)
        return CloudinaryService._instance

    def __init__(self):
        """Inicializa y configura Cloudinary si aún no está configurado."""
        if not CloudinaryService._configured:
            self._configure_cloudinary()
            CloudinaryService._configured = True

    def _configure_cloudinary(self) -> None:
        """Configura las credenciales de Cloudinary de forma robusta."""
        # IMPORTANTE: .strip() elimina espacios o saltos de línea invisibles
        cloud_name = settings.cloudinary.CLOUD_NAME.strip() if settings.cloudinary.CLOUD_NAME else None
        api_key = settings.cloudinary.API_KEY.strip() if settings.cloudinary.API_KEY else None
        api_secret = settings.cloudinary.API_SECRET.strip() if settings.cloudinary.API_SECRET else None

        if not all([cloud_name, api_key, api_secret]):
            logger.warning(
                "Cloudinary no está completamente configurado. "
                "Verifica las variables de entorno: CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET"
            )
            return

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)

        logger.debug(f"Cloudinary configurado para cloud: {cloud_name}")

    def _validate_configuration(self) -> None:
        """Valida que Cloudinary esté configurado antes de realizar operaciones."""
        if not all([settings.cloudinary.CLOUD_NAME, settings.cloudinary.API_KEY, settings.cloudinary.API_SECRET]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Servicio de imágenes no disponible. Cloudinary no está configurado.",
            )

    @staticmethod
    def _validate_image_format(file_bytes: bytes) -> tuple[str, str]:
        """
        Valida el formato de imagen basándose en magic numbers.

        Args:
            file_bytes: Bytes del archivo de imagen

        Returns:
            Tuple con (formato, content_type)

        Raises:
            HTTPException si el formato no es soportado
        """
        if len(file_bytes) < 12:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo de imagen inválido o corrupto")

        # Verificar magic numbers
        if file_bytes[:2] == b"\xff\xd8":
            return ("JPEG", "image/jpeg")
        elif file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return ("PNG", "image/png")
        elif file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
            return ("WEBP", "image/webp")
        elif file_bytes[:4] == b"GIF8":
            return ("GIF", "image/gif")
        elif file_bytes[:4] == b"\x00\x00\x00\x1c" or file_bytes[4:8] == b"ftyp":
            return ("AVIF", "image/avif")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de imagen no soportado. Usa JPEG, PNG, WEBP, GIF o AVIF.",
            )

    async def upload_image(
        self,
        file: UploadFile,
        folder: str = CloudinaryFolder.GENERAL,
        public_id: str | None = None,
        transformation: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        overwrite: bool = False,
        max_size_mb: float = 10.0,
    ) -> dict[str, Any]:
        """
        Sube una imagen a Cloudinary.

        Args:
            file: Archivo de imagen (UploadFile de FastAPI)
            folder: Carpeta destino en Cloudinary
            public_id: ID público personalizado (opcional)
            transformation: Transformaciones a aplicar
            tags: Etiquetas para la imagen
            overwrite: Si debe sobrescribir si ya existe
            max_size_mb: Tamaño máximo en MB

        Returns:
            Dict con información de la imagen subida:
            {
                "url": str,
                "secure_url": str,
                "public_id": str,
                "format": str,
                "width": int,
                "height": int,
                "bytes": int,
                "resource_type": str
            }

        Raises:
            HTTPException si hay error en la subida
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración antes de operar

        # Convertir folder de Enum a string si es necesario
        if isinstance(folder, CloudinaryFolder):
            folder = folder.value

        try:
            # Leer contenido del archivo
            file_bytes = await file.read()

            # Validar tamaño
            max_size_bytes = int(max_size_mb * 1024 * 1024)
            if len(file_bytes) > max_size_bytes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El archivo excede el tamaño máximo permitido ({max_size_mb} MB)",
                )

            # Validar formato
            self._validate_image_format(file_bytes)

            # Preparar opciones de subida
            upload_options: dict[str, Any] = {
                "folder": folder,
                "overwrite": overwrite,
                "resource_type": "image",
            }

            if public_id:
                upload_options["public_id"] = public_id

            if transformation:
                upload_options["transformation"] = transformation

            if tags:
                upload_options["tags"] = tags

            # Subir a Cloudinary
            result = cloudinary.uploader.upload(file_bytes, **upload_options)

            logger.info(
                f"Imagen subida exitosamente: {result.get('public_id')}",
                extra={
                    "public_id": result.get("public_id"),
                    "folder": folder,
                    "bytes": result.get("bytes"),
                    "format": result.get("format"),
                },
            )

            return {
                "url": result.get("url"),
                "secure_url": result.get("secure_url"),
                "public_id": result.get("public_id"),
                "format": result.get("format"),
                "width": result.get("width"),
                "height": result.get("height"),
                "bytes": result.get("bytes"),
                "resource_type": result.get("resource_type"),
                "created_at": result.get("created_at"),
                "version": result.get("version"),
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error subiendo imagen a Cloudinary: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al subir la imagen: {e!s}"
            )
        finally:
            # Resetear posición del archivo por si se necesita leer de nuevo
            await file.seek(0)

    async def upload_image_from_bytes(
        self,
        image_bytes: bytes,
        folder: str = CloudinaryFolder.GENERAL,
        public_id: str | None = None,
        transformation: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        overwrite: bool = False,
        max_size_mb: float = 10.0,
    ) -> dict[str, Any]:
        """
        Sube una imagen a Cloudinary desde bytes.

        Args:
            image_bytes: Bytes de la imagen
            folder: Carpeta destino en Cloudinary
            public_id: ID público personalizado
            transformation: Transformaciones a aplicar
            tags: Etiquetas para la imagen
            overwrite: Si debe sobrescribir si ya existe
            max_size_mb: Tamaño máximo en MB

        Returns:
            Dict con información de la imagen subida
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración

        # Convertir folder de Enum a string si es necesario
        if isinstance(folder, CloudinaryFolder):
            folder = folder.value

        try:
            # Validar tamaño
            max_size_bytes = int(max_size_mb * 1024 * 1024)
            if len(image_bytes) > max_size_bytes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El archivo excede el tamaño máximo permitido ({max_size_mb} MB)",
                )

            # Validar formato
            self._validate_image_format(image_bytes)

            # Preparar opciones
            upload_options: dict[str, Any] = {
                "folder": folder,
                "overwrite": overwrite,
                "resource_type": "image",
            }

            if public_id:
                upload_options["public_id"] = public_id

            if transformation:
                upload_options["transformation"] = transformation

            if tags:
                upload_options["tags"] = tags

            # Subir
            result = cloudinary.uploader.upload(image_bytes, **upload_options)

            logger.info(f"Imagen subida desde bytes: {result.get('public_id')}")

            return {
                "url": result.get("url"),
                "secure_url": result.get("secure_url"),
                "public_id": result.get("public_id"),
                "format": result.get("format"),
                "width": result.get("width"),
                "height": result.get("height"),
                "bytes": result.get("bytes"),
                "resource_type": result.get("resource_type"),
                "created_at": result.get("created_at"),
                "version": result.get("version"),
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error subiendo imagen desde bytes: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al subir la imagen: {e!s}"
            )

    async def upload_image_from_url(
        self,
        image_url: str,
        folder: str = CloudinaryFolder.GENERAL,
        public_id: str | None = None,
        transformation: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Sube una imagen a Cloudinary desde una URL.

        Args:
            image_url: URL de la imagen a subir
            folder: Carpeta destino en Cloudinary
            public_id: ID público personalizado
            transformation: Transformaciones a aplicar
            tags: Etiquetas para la imagen

        Returns:
            Dict con información de la imagen subida
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración

        # Convertir folder de Enum a string si es necesario
        if isinstance(folder, CloudinaryFolder):
            folder = folder.value

        try:
            upload_options: dict[str, Any] = {
                "folder": folder,
                "resource_type": "image",
            }

            if public_id:
                upload_options["public_id"] = public_id

            if transformation:
                upload_options["transformation"] = transformation

            if tags:
                upload_options["tags"] = tags

            result = cloudinary.uploader.upload(image_url, **upload_options)

            logger.info(f"Imagen subida desde URL: {result.get('public_id')}")

            return {
                "url": result.get("url"),
                "secure_url": result.get("secure_url"),
                "public_id": result.get("public_id"),
                "format": result.get("format"),
                "width": result.get("width"),
                "height": result.get("height"),
                "bytes": result.get("bytes"),
                "resource_type": result.get("resource_type"),
                "created_at": result.get("created_at"),
                "version": result.get("version"),
            }

        except Exception as e:
            logger.error(f"Error subiendo imagen desde URL: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al subir la imagen desde URL: {e!s}"
            )

    # async def upload_image_base64(
    #     self,
    #     base64_data: str,
    #     folder: str = CloudinaryFolder.GENERAL,
    #     public_id: Optional[str] = None,
    #     transformation: Optional[Dict[str, Any]] = None,
    #     tags: Optional[List[str]] = None,
    #     max_size_mb: float = 10.0
    # ) -> Dict[str, Any]:
    #     """
    #     Sube una imagen a Cloudinary desde base64.

    #     Args:
    #         base64_data: Imagen en formato base64 (con o sin prefijo data:image)
    #         folder: Carpeta destino
    #         public_id: ID público personalizado
    #         transformation: Transformaciones a aplicar
    #         tags: Etiquetas para la imagen
    #         max_size_mb: Tamaño máximo en MB

    #     Returns:
    #         Dict con información de la imagen subida
    #     """
    #     self._validate_configuration()

    #     try:
    #         # Limpiar prefijo data:image si existe
    #         if base64_data.startswith("data:"):
    #             base64_data = base64_data.split(",")[1]

    #         # Decodificar base64
    #         image_bytes = base64.b64decode(base64_data)

    #         # Usar el método de bytes
    #         return await self.upload_image_from_bytes(
    #             image_bytes=image_bytes,
    #             folder=folder,
    #             public_id=public_id,
    #             transformation=transformation,
    #             tags=tags,
    #             max_size_mb=max_size_mb
    #         )

    #     except HTTPException:
    #         raise
    #     except Exception as e:
    #         logger.error(f"Error procesando imagen base64: {str(e)}")
    #         raise HTTPException(
    #             status_code=status.HTTP_400_BAD_REQUEST,
    #             detail="Error al procesar la imagen en formato base64"
    #         )

    async def delete_image(self, public_id: str) -> dict[str, Any]:
        """
        Elimina una imagen de Cloudinary.

        Args:
            public_id: ID público de la imagen a eliminar

        Returns:
            Dict con resultado de la eliminación
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración

        try:
            result = cloudinary.uploader.destroy(public_id)

            if result.get("result") == "ok":
                logger.info(f"Imagen eliminada: {public_id}")
                return {"success": True, "public_id": public_id, "result": result.get("result")}
            else:
                logger.warning(f"No se pudo eliminar la imagen: {public_id}")
                return {"success": False, "public_id": public_id, "result": result.get("result")}

        except Exception as e:
            logger.error(f"Error eliminando imagen: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar la imagen: {e!s}"
            )

    async def delete_images_bulk(self, public_ids: list[str]) -> dict[str, Any]:
        """
        Elimina múltiples imágenes de Cloudinary.

        Args:
            public_ids: Lista de IDs públicos a eliminar

        Returns:
            Dict con resultados de la eliminación
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración

        if not public_ids:
            return {"deleted": [], "failed": []}

        try:
            result = cloudinary.api.delete_resources(public_ids)

            deleted = [k for k, v in result.get("deleted", {}).items() if v == "deleted"]
            failed = [k for k, v in result.get("deleted", {}).items() if v != "deleted"]

            logger.info(f"Eliminación masiva: {len(deleted)} exitosas, {len(failed)} fallidas")

            return {"deleted": deleted, "failed": failed, "deleted_count": len(deleted), "failed_count": len(failed)}

        except Exception as e:
            logger.error(f"Error en eliminación masiva: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar las imágenes: {e!s}"
            )

    def get_optimized_url(
        self,
        public_id: str,
        width: int | None = None,
        height: int | None = None,
        crop: str = "fill",
        quality: str = "auto",
        format: str = ImageFormat.AUTO,
        gravity: str = "auto",
    ) -> str:
        """
        Genera una URL optimizada para una imagen.

        Args:
            public_id: ID público de la imagen
            width: Ancho deseado
            height: Alto deseado
            crop: Modo de recorte (fill, fit, scale, crop, thumb, etc.)
            quality: Calidad (auto, auto:low, auto:eco, auto:good, auto:best)
            format: Formato de salida
            gravity: Punto de enfoque (auto, face, center, etc.)

        Returns:
            URL optimizada de la imagen
        """
        transformation = []

        if width or height:
            transform: dict[str, Any] = {"crop": crop, "gravity": gravity}
            if width:
                transform["width"] = width
            if height:
                transform["height"] = height
            transformation.append(transform)

        transformation.append({"quality": quality, "fetch_format": format})

        url, _ = cloudinary_url(public_id, transformation=transformation, secure=True)

        return url

    def get_thumbnail_url(self, public_id: str, width: int = 150, height: int = 150) -> str:
        """
        Genera una URL de miniatura para una imagen.

        Args:
            public_id: ID público de la imagen
            width: Ancho de la miniatura
            height: Alto de la miniatura

        Returns:
            URL de la miniatura
        """
        return self.get_optimized_url(public_id=public_id, width=width, height=height, crop="thumb", gravity="face")

    async def get_image_info(self, public_id: str) -> dict[str, Any]:
        """
        Obtiene información detallada de una imagen.

        Args:
            public_id: ID público de la imagen

        Returns:
            Dict con información de la imagen
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración

        try:
            result = cloudinary.api.resource(public_id)

            return {
                "public_id": result.get("public_id"),
                "format": result.get("format"),
                "version": result.get("version"),
                "resource_type": result.get("resource_type"),
                "type": result.get("type"),
                "created_at": result.get("created_at"),
                "bytes": result.get("bytes"),
                "width": result.get("width"),
                "height": result.get("height"),
                "url": result.get("url"),
                "secure_url": result.get("secure_url"),
                "folder": result.get("folder"),
                "tags": result.get("tags", []),
            }

        except cloudinary.api.NotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Imagen no encontrada: {public_id}")
        except Exception as e:
            logger.error(f"Error obteniendo info de imagen: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al obtener información de la imagen: {e!s}",
            )

    async def list_images_in_folder(
        self, folder: str, max_results: int = 100, next_cursor: str | None = None
    ) -> dict[str, Any]:
        """
        Lista todas las imágenes en una carpeta.

        Args:
            folder: Carpeta a listar
            max_results: Número máximo de resultados
            next_cursor: Cursor para paginación

        Returns:
            Dict con lista de imágenes y cursor de paginación
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración

        try:
            options = {"type": "upload", "prefix": folder, "max_results": min(max_results, 500)}

            if next_cursor:
                options["next_cursor"] = next_cursor

            result = cloudinary.api.resources(**options)

            images = [
                {
                    "public_id": r.get("public_id"),
                    "format": r.get("format"),
                    "url": r.get("url"),
                    "secure_url": r.get("secure_url"),
                    "bytes": r.get("bytes"),
                    "width": r.get("width"),
                    "height": r.get("height"),
                    "created_at": r.get("created_at"),
                }
                for r in result.get("resources", [])
            ]

            return {
                "images": images,
                "total_count": len(images),
                "next_cursor": result.get("next_cursor"),
                "has_more": result.get("next_cursor") is not None,
            }

        except Exception as e:
            logger.error(f"Error listando imágenes: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al listar imágenes: {e!s}"
            )

    async def rename_image(self, from_public_id: str, to_public_id: str, overwrite: bool = False) -> dict[str, Any]:
        """
        Renombra una imagen en Cloudinary.

        Args:
            from_public_id: ID público actual
            to_public_id: Nuevo ID público
            overwrite: Si debe sobrescribir si ya existe

        Returns:
            Dict con resultado del renombrado
        """
        self._validate_configuration()
        self._configure_cloudinary()  # Forzar configuración

        try:
            result = cloudinary.uploader.rename(from_public_id, to_public_id, overwrite=overwrite)

            logger.info(f"Imagen renombrada: {from_public_id} -> {to_public_id}")

            return {
                "success": True,
                "public_id": result.get("public_id"),
                "url": result.get("url"),
                "secure_url": result.get("secure_url"),
            }

        except Exception as e:
            logger.error(f"Error renombrando imagen: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al renombrar la imagen: {e!s}"
            )

    def health_check(self) -> dict[str, Any]:
        """
        Verifica el estado de la conexión con Cloudinary.

        Returns:
            Dict con estado del servicio
        """
        try:
            if not all([settings.cloudinary.CLOUD_NAME, settings.cloudinary.API_KEY, settings.cloudinary.API_SECRET]):
                return {"status": "not_configured", "message": "Cloudinary no está configurado"}

            # Intentar obtener información de la cuenta
            result = cloudinary.api.ping()

            return {"status": "healthy", "cloud_name": settings.cloudinary.CLOUD_NAME, "response": result}

        except Exception as e:
            return {"status": "error", "message": str(e)}


# Instancia global del servicio (Singleton)
cloudinary_service = CloudinaryService()
