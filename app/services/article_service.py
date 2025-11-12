from typing import Any, Dict, List, Optional
from decimal import Decimal

from fastapi import HTTPException, status

from app.config.logging_config import get_logger
from app.schemas.article import (
    ArticleDetail,
    ArticleImageResponse,
    ArticleListResponse,
    ArticlePriceDetail,
    ArticleStockDetail,
    ArticleSummary,
    ImageUploadResponse,
)
from app.services.source_system_service import source_system_service

from app.config.settings import Settings
settings = Settings()
class ArticleService:
    """Servicio de negocio para artículos provenientes de Profit Plus."""

    def __init__(self):
        self.logger = get_logger("articles")
        self._source_service = source_system_service

    @staticmethod
    def _build_image_url(rowguid: Optional[str]) -> Optional[str]:
        """
        Construye la URL completa para servir una imagen por su GUID.
        """
        if not rowguid:
            return None
        
        # Normalizar el GUID: convertir a string, limpiar y remover llaves
        guid_str = str(rowguid).strip().upper().replace('{', '').replace('}', '')
        if not guid_str:
            return None
        
        base_url = settings.API_URL or "http://localhost:8000"
        # CORREGIDO: La ruta debe incluir /articles porque el router está registrado con ese prefijo
        url = f"{base_url}/api/v1/articles/images/{guid_str}"
        return url

    @staticmethod
    def _to_decimal(value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def get_catalog(
        self,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        line_code: Optional[str] = None,
        category_code: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        sort_by: str = "art_des",
        price_code: str = "01",
        warehouse_code: str = "001",
    ) -> ArticleListResponse:
        """Obtiene el catálogo paginado directamente desde Profit Plus."""
        result = self._source_service.get_articles_catalog(
            page=page,
            limit=limit,
            search=search,
            line_code=line_code,
            category_code=category_code,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            price_code=price_code,
            warehouse_code=warehouse_code,
        )

        summaries: List[ArticleSummary] = []
        for row in result["items"]:
            co_art = (row.get("co_art") or "").strip()
            art_des = row.get("art_des") or ""
            category_code = (row.get("category_code") or "").strip() or None
            category_name = row.get("category_name")
            price = self._to_decimal(row.get("price"))
            currency = (row.get("currency") or "VES").strip()
            stock = self._to_decimal(row.get("stock"))
            warehouse = (row.get("warehouse_code") or "").strip() or None
            image_guid = row.get("image_guid")
            
            # Normalizar el GUID si existe
            image_guid_normalized = None
            if image_guid:
                image_guid_normalized = str(image_guid).strip().upper().replace('{', '').replace('}', '')
            
            image_url = self._build_image_url(image_guid_normalized)
            
            summaries.append(
                ArticleSummary(
                    co_art=co_art,
                    art_des=art_des,
                    category_code=category_code,
                    category_name=category_name,
                    price=price,
                    currency=currency,
                    stock=stock,
                    warehouse_code=warehouse,
                    image_url=image_url,
                    has_image=bool(image_guid_normalized),
                )
            )

        total = result.get("total", 0)
        total_pages = (total + limit - 1) // limit if total else 0

        filters_applied: Dict[str, Any] = {}
        if search:
            filters_applied["search"] = search
        if line_code:
            filters_applied["co_lin"] = line_code
        if category_code:
            filters_applied["co_cat"] = category_code
        if min_price is not None:
            filters_applied["min_price"] = str(min_price)
        if max_price is not None:
            filters_applied["max_price"] = str(max_price)
        filters_applied["sort_by"] = sort_by
        filters_applied["price_code"] = price_code
        filters_applied["warehouse_code"] = warehouse_code

        return ArticleListResponse(
            articles=summaries,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
            filters_applied=filters_applied,
        )

    def get_article_detail(self, co_art: str) -> ArticleDetail:
        """Obtiene el detalle de un artículo y lo transforma a schema."""
        detail = self._source_service.get_article_detail(co_art)
        if not detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artículo no encontrado en Profit Plus",
            )

        header = detail["header"]
        prices_raw = detail["prices"]
        stock_raw = detail["stock"]
        images_raw = detail["images"]

        prices = [
            ArticlePriceDetail(
                price_code=(item.get("price_code") or "").strip(),
                price_name=item.get("price_name"),
                amount=self._to_decimal(item.get("amount")) or Decimal("0"),
                currency=(item.get("currency") or "VES").strip(),
                desde=item.get("desde"),  # Fecha desde la cual es válido el precio
            )
            for item in prices_raw
        ]

        stock = [
            ArticleStockDetail(
                warehouse_code=(item.get("warehouse_code") or "").strip(),
                warehouse_name=item.get("warehouse_name"),
                quantity=self._to_decimal(item.get("quantity")) or Decimal("0"),
            )
            for item in stock_raw
        ]

        images = self._map_images(images_raw)

        # Construir datos adicionales solo con campos que existen
        additional_data = {}
        if header.get("tipo"):
            additional_data["tipo"] = header.get("tipo")
        if header.get("fecha_reg"):
            additional_data["fecha_reg"] = str(header.get("fecha_reg"))

        return ArticleDetail(
            co_art=(header.get("co_art") or "").strip(),
            art_des=header.get("art_des") or "",
            modelo=(header.get("modelo") or "").strip() if header.get("modelo") else None,
            ref=header.get("ref"),
            category_code=(header.get("co_cat") or "").strip() or None,
            category_name=header.get("category_name"),
            line_code=(header.get("co_lin") or "").strip() or None,
            sub_line_code=(header.get("co_subl") or "").strip() or None,
            presentation=None,  # Campo no disponible en saArticulo
            additional_data=additional_data,
            prices=prices,
            stock_by_warehouse=stock,
            images=images,
        )

    def upload_image(
        self,
        co_art: str,
        image_bytes: bytes,
        filename: Optional[str],
        tip: Optional[str] = None,
        created_by: str = "API_USER",
    ) -> ImageUploadResponse:
        """Sube una imagen para un artículo y devuelve la respuesta de negocio."""
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo de imagen está vacío",
            )

        try:
            guid = self._source_service.upload_article_image(
                article_code=co_art,
                image_bytes=image_bytes,
                description=filename,
                tip=tip,
                created_by=created_by,
            )
        except ValueError as e:
            # Capturar errores de tip duplicado o problemas de generación
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        return ImageUploadResponse(
            message="Imagen subida correctamente",
            image_guid=guid,
            url=self._build_image_url(guid),
        )

    def get_image_binary(self, image_guid: str) -> Dict[str, Any]:
        """Obtiene la imagen binaria y metadatos para servirla por HTTP."""
        row = self._source_service.get_image_by_guid(image_guid)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Imagen no encontrada",
            )
        if not row.get("picture"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Imagen sin contenido",
            )
        return row

    def _map_images(self, rows: List[Dict[str, Any]]) -> List[ArticleImageResponse]:
        """Convierte las filas de saArtImagen a schemas de respuesta."""
        images: List[ArticleImageResponse] = []
        for row in rows:
            guid = row.get("rowguid")
            if not guid:
                continue
            # Normalizar el GUID a string consistente
            guid_str = str(guid).strip().upper().replace('{', '').replace('}', '')
            url = self._build_image_url(guid_str)
            images.append(
                ArticleImageResponse(
                    guid=guid_str,
                    url=url,
                    description=row.get("imagen_des"),
                    tip=row.get("tip"),
                )
            )
        return images


article_service = ArticleService()

