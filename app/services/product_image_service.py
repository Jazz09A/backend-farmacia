"""
Servicio para gestionar imágenes de productos.

Combina:
- Subida de imágenes a Cloudinary
- Almacenamiento de referencias en la base de datos local (DATABASE_URL)
- Integración con códigos de artículos de Profit Plus
"""

from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.config.logging_config import get_logger
from app.models.product_image import ProductImage
from app.services.cache_service import cache_service
from app.services.cloudinary_service import CloudinaryFolder, cloudinary_service

logger = get_logger("product_image_service")


class ProductImageService:
    """
    Servicio para gestionar imágenes de productos.

    Flujo:
    1. Recibe imagen + código de artículo de Profit Plus (co_art)
    2. Sube la imagen a Cloudinary
    3. Guarda la referencia (URL + public_id) en la base de datos local
    4. Permite recuperar imágenes por co_art para combinar con datos de Profit
    """

    def __init__(self, db: Session | None = None):
        """
        Inicializa el servicio.

        Args:
            db: Sesión de base de datos (opcional, se crea si no se proporciona)
        """
        self._db = db
        self._owns_session = False

    def _get_db(self) -> Session:
        """Obtiene o crea una sesión de base de datos."""
        if self._db is None:
            self._db = SessionLocal()
            self._owns_session = True
        return self._db

    def _close_db(self):
        """Cierra la sesión si fue creada por el servicio."""
        if self._owns_session and self._db is not None:
            self._db.close()
            self._db = None
            self._owns_session = False

    async def upload_product_image(
        self,
        co_art: str,
        file: UploadFile,
        is_main: bool = False,
        description: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """
        Sube una imagen de producto a Cloudinary y guarda la referencia en DB.

        Args:
            co_art: Código del artículo en Profit Plus
            file: Archivo de imagen
            is_main: Si es la imagen principal del producto
            description: Descripción o alt text de la imagen
            created_by: Usuario que sube la imagen

        Returns:
            Dict con información de la imagen subida
        """
        if not co_art or not co_art.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="El código de artículo (co_art) es requerido"
            )

        # Normalizar código de artículo
        co_art_normalized = co_art.strip().upper()

        try:
            db = self._get_db()

            # Si es imagen principal, desmarcar las anteriores principales
            if is_main:
                db.query(ProductImage).filter(
                    and_(ProductImage.co_art_profit == co_art_normalized, ProductImage.is_main)
                ).update({"is_main": False})

            # Contar imágenes existentes para generar public_id único
            image_count = db.query(ProductImage).filter(ProductImage.co_art_profit == co_art_normalized).count()

            # Generar public_id personalizado para Cloudinary
            public_id = f"{co_art_normalized}_{image_count + 1}"

            # Subir a Cloudinary (Simplificado para descartar error de firma)
            cloudinary_result = await cloudinary_service.upload_image(
                file=file,
                folder=CloudinaryFolder.PRODUCTS.value,  # Usar .value para obtener el string
                public_id=public_id,
                # Temporalmente comentados para probar firma limpia
                # tags=[co_art_normalized, "producto", "farmaplus"],
                overwrite=True,
            )

            # Crear registro en la base de datos (estructura simple)
            product_image = ProductImage(
                co_art_profit=co_art_normalized,
                cloudinary_url=cloudinary_result["secure_url"],
                is_main=is_main,
            )

            db.add(product_image)
            db.commit()
            db.refresh(product_image)

            logger.info(
                f"Imagen subida para artículo {co_art_normalized}",
                extra={
                    "co_art": co_art_normalized,
                    "image_id": product_image.id,
                    "cloudinary_public_id": cloudinary_result["public_id"],
                    "is_main": is_main,
                },
            )

            # Invalidar cache del artículo ya que cambió su información de imágenes
            # Esto permite que los cambios se vean inmediatamente sin esperar a que expire el cache
            cache_key = cache_service._generate_key("article", co_art_normalized)
            invalidated = cache_service.invalidate(cache_key)
            # También invalidar cualquier catálogo que pueda incluir este artículo
            catalog_invalidated = cache_service.invalidate_pattern("catalog:")
            logger.info(
                f"Cache invalidado - artículo {co_art_normalized}: "
                f"detalle={'invalidado' if invalidated else 'no encontrado'}, "
                f"catálogos invalidados={catalog_invalidated}"
            )

            return {
                "id": product_image.id,
                "co_art_profit": product_image.co_art_profit,
                "cloudinary_url": product_image.cloudinary_url,
                "cloudinary_public_id": cloudinary_result["public_id"],  # Guardamos el public_id de cloudinary
                "is_main": product_image.is_main,
                "display_order": image_count,  # Orden basado en la cantidad de imágenes
                "description": description,  # Pasamos la descripción aunque no se guarde en DB
                "created_at": None,
                "cloudinary_info": {
                    "width": cloudinary_result.get("width"),
                    "height": cloudinary_result.get("height"),
                    "format": cloudinary_result.get("format"),
                    "bytes": cloudinary_result.get("bytes"),
                },
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error subiendo imagen de producto: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al subir la imagen: {e!s}"
            )

    async def upload_product_image_from_url(
        self,
        co_art: str,
        image_url: str,
        is_main: bool = False,
        description: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """
        Sube una imagen de producto desde URL a Cloudinary.

        Args:
            co_art: Código del artículo en Profit Plus
            image_url: URL de la imagen a subir
            is_main: Si es la imagen principal
            description: Descripción de la imagen
            created_by: Usuario que sube la imagen

        Returns:
            Dict con información de la imagen subida
        """
        if not co_art or not co_art.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="El código de artículo (co_art) es requerido"
            )

        co_art_normalized = co_art.strip().upper()

        try:
            db = self._get_db()

            if is_main:
                db.query(ProductImage).filter(
                    and_(ProductImage.co_art_profit == co_art_normalized, ProductImage.is_main)
                ).update({"is_main": False})

            image_count = db.query(ProductImage).filter(ProductImage.co_art_profit == co_art_normalized).count()

            public_id = f"{co_art_normalized}_{image_count + 1}"

            # Subir desde URL a Cloudinary (Simplificado para descartar error de firma)
            cloudinary_result = await cloudinary_service.upload_image_from_url(
                image_url=image_url,
                folder=CloudinaryFolder.PRODUCTS.value,  # Usar .value para obtener el string
                public_id=public_id,
                # Temporalmente comentados para probar firma limpia
                # tags=[co_art_normalized, "producto", "farmaplus"]
            )

            # Crear registro en la base de datos (estructura simple)
            product_image = ProductImage(
                co_art_profit=co_art_normalized,
                cloudinary_url=cloudinary_result["secure_url"],
                is_main=is_main,
            )

            db.add(product_image)
            db.commit()
            db.refresh(product_image)

            logger.info(f"Imagen subida desde URL para artículo {co_art_normalized}")

            # Invalidar cache del artículo ya que cambió su información de imágenes
            # Esto permite que los cambios se vean inmediatamente sin esperar a que expire el cache
            cache_key = cache_service._generate_key("article", co_art_normalized)
            invalidated = cache_service.invalidate(cache_key)
            # También invalidar cualquier catálogo que pueda incluir este artículo
            catalog_invalidated = cache_service.invalidate_pattern("catalog:")
            logger.info(
                f"Cache invalidado - artículo {co_art_normalized}: "
                f"detalle={'invalidado' if invalidated else 'no encontrado'}, "
                f"catálogos invalidados={catalog_invalidated}"
            )

            return {
                "id": product_image.id,
                "co_art_profit": product_image.co_art_profit,
                "cloudinary_url": product_image.cloudinary_url,
                "cloudinary_public_id": cloudinary_result["public_id"],
                "is_main": product_image.is_main,
                "display_order": image_count,
                "description": description,
                "created_at": None,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error subiendo imagen desde URL: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al subir la imagen: {e!s}"
            )

    def get_images_by_article(self, co_art: str, db: Session | None = None) -> list[dict[str, Any]]:
        """
        Obtiene todas las imágenes de un artículo.

        Args:
            co_art: Código del artículo en Profit Plus
            db: Sesión de base de datos (opcional)

        Returns:
            Lista de imágenes del artículo
        """
        if not co_art:
            return []

        co_art_normalized = co_art.strip().upper()

        try:
            session = db or self._get_db()

            logger.debug(f"Buscando imágenes para artículo: {co_art_normalized}")

            images = (
                session.query(ProductImage)
                .filter(ProductImage.co_art_profit == co_art_normalized)
                .order_by(
                    ProductImage.is_main.desc(),  # Principales primero
                    ProductImage.id.asc(),  # Luego por ID (orden de creación)
                )
                .all()
            )

            logger.debug(f"Encontradas {len(images)} imágenes para artículo {co_art_normalized}")

            result = [
                {
                    "id": img.id,
                    "co_art_profit": img.co_art_profit,
                    "cloudinary_url": img.cloudinary_url,
                    "cloudinary_public_id": None,  # No almacenado en DB actual
                    "is_main": img.is_main,
                    "display_order": idx,  # Usar índice como orden
                    "description": None,  # No almacenado en DB actual
                    "created_at": None,  # No almacenado en DB actual
                }
                for idx, img in enumerate(images)
            ]

            if result:
                logger.info(f"Imágenes encontradas para {co_art_normalized}: {len(result)} imágenes")
            else:
                logger.debug(f"No se encontraron imágenes en Cloudinary para {co_art_normalized}")

            return result

        except Exception as e:
            logger.error(f"Error obteniendo imágenes del artículo {co_art}: {e!s}", exc_info=True)
            return []

    def get_main_image_by_article(self, co_art: str, db: Session | None = None) -> dict[str, Any] | None:
        """
        Obtiene la imagen principal de un artículo.

        Args:
            co_art: Código del artículo
            db: Sesión de base de datos

        Returns:
            Información de la imagen principal o None
        """
        if not co_art:
            return None

        co_art_normalized = co_art.strip().upper()

        try:
            session = db or self._get_db()

            # Primero buscar la marcada como principal
            image = (
                session.query(ProductImage)
                .filter(and_(ProductImage.co_art_profit == co_art_normalized, ProductImage.is_main))
                .first()
            )

            # Si no hay principal, tomar la primera por ID
            if not image:
                image = (
                    session.query(ProductImage)
                    .filter(ProductImage.co_art_profit == co_art_normalized)
                    .order_by(ProductImage.id.asc())
                    .first()
                )

            if not image:
                return None

            return {
                "id": image.id,
                "co_art_profit": image.co_art_profit,
                "cloudinary_url": image.cloudinary_url,
                "cloudinary_public_id": None,
                "is_main": image.is_main,
                "display_order": 0,
                "description": None,
            }

        except Exception as e:
            logger.error(f"Error obteniendo imagen principal: {e!s}")
            return None

    def get_images_by_articles_batch(
        self, co_arts: list[str], db: Session | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Obtiene imágenes de múltiples artículos en una sola consulta (optimizado).

        Args:
            co_arts: Lista de códigos de artículos
            db: Sesión de base de datos

        Returns:
            Dict[co_art] -> List[imágenes]
        """
        if not co_arts:
            return {}

        # Normalizar códigos
        normalized_codes = [code.strip().upper() for code in co_arts if code]
        if not normalized_codes:
            return {}

        try:
            session = db or self._get_db()

            images = (
                session.query(ProductImage)
                .filter(ProductImage.co_art_profit.in_(normalized_codes))
                .order_by(ProductImage.co_art_profit, ProductImage.is_main.desc(), ProductImage.id.asc())
                .all()
            )

            # Agrupar por co_art
            result: dict[str, list[dict[str, Any]]] = {}
            order_counter: dict[str, int] = {}

            for img in images:
                co_art = img.co_art_profit
                if co_art not in result:
                    result[co_art] = []
                    order_counter[co_art] = 0

                result[co_art].append(
                    {
                        "id": img.id,
                        "cloudinary_url": img.cloudinary_url,
                        "cloudinary_public_id": None,
                        "is_main": img.is_main,
                        "display_order": order_counter[co_art],
                        "description": None,
                    }
                )
                order_counter[co_art] += 1

            return result

        except Exception as e:
            logger.error(f"Error en consulta batch de imágenes: {e!s}")
            return {}

    def get_main_images_by_articles_batch(self, co_arts: list[str], db: Session | None = None) -> dict[str, str]:
        """
        Obtiene solo la URL de la imagen principal de múltiples artículos.
        Optimizado para catálogos.

        Args:
            co_arts: Lista de códigos de artículos
            db: Sesión de base de datos

        Returns:
            Dict[co_art] -> cloudinary_url de la imagen principal
        """
        if not co_arts:
            return {}

        normalized_codes = [code.strip().upper() for code in co_arts if code]
        if not normalized_codes:
            return {}

        try:
            session = db or self._get_db()

            # Obtener todas las imágenes de los artículos
            images = (
                session.query(ProductImage)
                .filter(ProductImage.co_art_profit.in_(normalized_codes))
                .order_by(ProductImage.co_art_profit, ProductImage.is_main.desc(), ProductImage.id.asc())
                .all()
            )

            # Para cada artículo, tomar solo la primera imagen (que será la principal o la primera por ID)
            result: dict[str, str] = {}
            for img in images:
                co_art = img.co_art_profit
                if co_art not in result:  # Solo tomar la primera
                    result[co_art] = img.cloudinary_url

            return result

        except Exception as e:
            logger.error(f"Error obteniendo imágenes principales batch: {e!s}")
            return {}

    @staticmethod
    def _extract_public_id_from_url(cloudinary_url: str) -> str | None:
        """
        Extrae el public_id de una URL de Cloudinary.

        URL típica: https://res.cloudinary.com/cloud_name/image/upload/v123456789/folder/public_id.format
        """
        try:
            if not cloudinary_url:
                return None

            # Buscar la parte después de /upload/
            if "/upload/" in cloudinary_url:
                parts = cloudinary_url.split("/upload/")[1]
                # Remover la versión si existe (v123456789/)
                if parts.startswith("v") and "/" in parts:
                    parts = "/".join(parts.split("/")[1:])
                # Remover la extensión del archivo
                if "." in parts:
                    parts = ".".join(parts.split(".")[:-1])
                return parts
            return None
        except Exception:
            return None

    async def delete_image(self, image_id: int, db: Session | None = None) -> dict[str, Any]:
        """
        Elimina una imagen de producto (de Cloudinary y de la DB).

        Args:
            image_id: ID de la imagen en la base de datos
            db: Sesión de base de datos

        Returns:
            Resultado de la eliminación
        """
        try:
            session = db or self._get_db()

            image = session.query(ProductImage).filter(ProductImage.id == image_id).first()

            if not image:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Imagen no encontrada")

            # Extraer public_id de la URL para eliminar de Cloudinary
            cloudinary_deleted = False
            public_id = self._extract_public_id_from_url(image.cloudinary_url)

            if public_id:
                try:
                    await cloudinary_service.delete_image(public_id)
                    cloudinary_deleted = True
                except Exception as e:
                    logger.warning(f"No se pudo eliminar de Cloudinary: {e!s}")

            co_art = image.co_art_profit

            # Eliminar de la base de datos
            session.delete(image)
            session.commit()

            logger.info(f"Imagen {image_id} eliminada para artículo {co_art}")

            # Invalidar cache del artículo ya que cambió su información de imágenes
            # Esto permite que los cambios se vean inmediatamente sin esperar a que expire el cache
            co_art_normalized = co_art.strip().upper() if co_art else ""
            if co_art_normalized:
                cache_key = cache_service._generate_key("article", co_art_normalized)
                invalidated = cache_service.invalidate(cache_key)
                # También invalidar cualquier catálogo que pueda incluir este artículo
                catalog_invalidated = cache_service.invalidate_pattern("catalog:")
                logger.info(
                    f"Cache invalidado - artículo {co_art_normalized}: "
                    f"detalle={'invalidado' if invalidated else 'no encontrado'}, "
                    f"catálogos invalidados={catalog_invalidated}"
                )

            return {
                "success": True,
                "message": "Imagen eliminada correctamente",
                "image_id": image_id,
                "co_art_profit": co_art,
                "cloudinary_deleted": cloudinary_deleted,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error eliminando imagen: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar la imagen: {e!s}"
            )

    async def set_main_image(self, image_id: int, db: Session | None = None) -> dict[str, Any]:
        """
        Establece una imagen como principal para su artículo.

        Args:
            image_id: ID de la imagen
            db: Sesión de base de datos

        Returns:
            Información de la imagen actualizada
        """
        try:
            session = db or self._get_db()

            image = session.query(ProductImage).filter(ProductImage.id == image_id).first()

            if not image:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Imagen no encontrada")

            # Desmarcar otras imágenes del mismo artículo
            session.query(ProductImage).filter(
                and_(ProductImage.co_art_profit == image.co_art_profit, ProductImage.id != image_id)
            ).update({"is_main": False})

            # Marcar esta como principal
            image.is_main = True
            session.commit()

            logger.info(f"Imagen {image_id} establecida como principal para {image.co_art_profit}")

            # Invalidar cache del artículo ya que cambió su información de imágenes
            # Esto permite que los cambios se vean inmediatamente sin esperar a que expire el cache
            co_art_normalized = image.co_art_profit.strip().upper() if image.co_art_profit else ""
            if co_art_normalized:
                cache_key = cache_service._generate_key("article", co_art_normalized)
                invalidated = cache_service.invalidate(cache_key)
                # También invalidar cualquier catálogo que pueda incluir este artículo
                catalog_invalidated = cache_service.invalidate_pattern("catalog:")
                logger.info(
                    f"Cache invalidado - artículo {co_art_normalized}: "
                    f"detalle={'invalidado' if invalidated else 'no encontrado'}, "
                    f"catálogos invalidados={catalog_invalidated}"
                )

            return {
                "success": True,
                "message": "Imagen establecida como principal",
                "image_id": image_id,
                "co_art_profit": image.co_art_profit,
                "cloudinary_url": image.cloudinary_url,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error estableciendo imagen principal: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al actualizar la imagen: {e!s}"
            )

    async def delete_all_images_by_article(self, co_art: str, db: Session | None = None) -> dict[str, Any]:
        """
        Elimina todas las imágenes de un artículo.

        Args:
            co_art: Código del artículo
            db: Sesión de base de datos

        Returns:
            Resultado de la eliminación
        """
        if not co_art:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El código de artículo es requerido")

        co_art_normalized = co_art.strip().upper()

        try:
            session = db or self._get_db()

            images = session.query(ProductImage).filter(ProductImage.co_art_profit == co_art_normalized).all()

            if not images:
                return {
                    "success": True,
                    "message": "No hay imágenes para eliminar",
                    "co_art_profit": co_art_normalized,
                    "deleted_count": 0,
                }

            # Extraer public_ids de las URLs para eliminar de Cloudinary
            public_ids_raw = [
                self._extract_public_id_from_url(img.cloudinary_url) for img in images if img.cloudinary_url
            ]
            public_ids = [pid for pid in public_ids_raw if pid]  # Filtrar None

            # Eliminar de Cloudinary en batch
            cloudinary_result = None
            if public_ids:
                try:
                    cloudinary_result = await cloudinary_service.delete_images_bulk(public_ids)
                except Exception as e:
                    logger.warning(f"Error eliminando de Cloudinary: {e!s}")

            # Eliminar de la base de datos
            deleted_count = session.query(ProductImage).filter(ProductImage.co_art_profit == co_art_normalized).delete()

            session.commit()

            logger.info(f"Eliminadas {deleted_count} imágenes del artículo {co_art_normalized}")

            # Invalidar cache del artículo ya que cambió su información de imágenes
            # Esto permite que los cambios se vean inmediatamente sin esperar a que expire el cache
            cache_key = cache_service._generate_key("article", co_art_normalized)
            invalidated = cache_service.invalidate(cache_key)
            # También invalidar cualquier catálogo que pueda incluir este artículo
            catalog_invalidated = cache_service.invalidate_pattern("catalog:")
            logger.info(
                f"Cache invalidado - artículo {co_art_normalized}: "
                f"detalle={'invalidado' if invalidated else 'no encontrado'}, "
                f"catálogos invalidados={catalog_invalidated}"
            )

            return {
                "success": True,
                "message": f"Se eliminaron {deleted_count} imágenes",
                "co_art_profit": co_art_normalized,
                "deleted_count": deleted_count,
                "cloudinary_result": cloudinary_result,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error eliminando imágenes del artículo: {e!s}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar las imágenes: {e!s}"
            )


# Instancia global del servicio
product_image_service = ProductImageService()
