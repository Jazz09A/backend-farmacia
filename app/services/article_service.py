from typing import Any, Dict, List, Optional
from decimal import Decimal
import json
import os
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.config.logging_config import get_logger
from app.schemas.article import (
    ArticleDetail,
    ArticleImageResponse,
    ArticleListResponse,
    ArticlePriceDetail,
    ArticleStockDetail,
    ArticleSummary,
    ImageUploadResponse,
    CloudinaryImageInfo,
)
from app.schemas.product import FlashOfferInfo, ProfitDiscountInfo
from app.models.promotion import FlashOffer, DiscountType
from app.services.source_system_service import source_system_service
from app.services.cache_service import cache_service
from app.services.product_image_service import product_image_service
from app.utils.timezone import get_ve_now
# from app.querys.image_query import get_image_by_co_art
from app.config.settings import Settings
settings = Settings()
class ArticleService:
    """Servicio de negocio para artículos provenientes de Profit Plus."""

    def __init__(self):
        self.logger = get_logger("articles")
        self._source_service = source_system_service
        self._descriptions_cache: Optional[Dict[str, str]] = None
        self._descriptions_file_path = Path("articles_with_descriptions.json")
    
    def _get_active_flash_offers_by_article_codes(
        self, 
        db: Optional[Session], 
        article_codes: List[str]
    ) -> Dict[str, FlashOffer]:
        """
        Obtiene flash offers activas para una lista de códigos de artículo de manera optimizada.
        
        Returns:
            Dict[str, FlashOffer]: Mapa de article_code -> FlashOffer
        """
        if not db or not article_codes:
            return {}
        
        now = get_ve_now()
        
        # Normalizar códigos de artículo
        normalized_codes = [code.upper().strip() for code in article_codes if code]
        if not normalized_codes:
            return {}
        
        # Obtener flash offers activas por article_code (una sola consulta optimizada)
        flash_offers = db.query(FlashOffer).filter(
            and_(
                FlashOffer.article_code.in_(normalized_codes),
                FlashOffer.is_active == True,
                FlashOffer.start_time <= now,
                FlashOffer.end_time >= now,
                or_(
                    FlashOffer.max_quantity.is_(None),
                    FlashOffer.used_quantity < FlashOffer.max_quantity
                )
            )
        ).all()
        
        # Crear mapa article_code -> FlashOffer
        result = {}
        for offer in flash_offers:
            normalized_code = (offer.article_code or "").upper().strip()
            if normalized_code and normalized_code not in result:
                result[normalized_code] = offer
        
        return result
    
    def _build_flash_offer_info(
        self, 
        flash_offer: FlashOffer, 
        original_price: Decimal
    ) -> FlashOfferInfo:
        """Construye la información de flash offer para incluir en la respuesta del artículo."""
        original_price_float = float(original_price)
        
        # Determinar el tipo de descuento
        discount_type_value = flash_offer.discount_type
        if hasattr(discount_type_value, 'value'):
            discount_type_value = discount_type_value.value
        
        # Calcular precio con descuento
        if discount_type_value == 'percentage' or discount_type_value == DiscountType.PERCENTAGE.value:
            discount_amount = original_price_float * (flash_offer.discount_value / 100)
            discount_percentage = flash_offer.discount_value
        else:  # fixed
            discount_amount = min(flash_offer.discount_value, original_price_float)
            discount_percentage = (discount_amount / original_price_float * 100) if original_price_float > 0 else 0
        
        offer_price = original_price_float - discount_amount
        
        return FlashOfferInfo(
            id=flash_offer.id,
            discount_type=discount_type_value,
            discount_value=flash_offer.discount_value,
            original_price=original_price_float,
            offer_price=round(offer_price, 2),
            discount_percentage=round(discount_percentage, 2),
            end_time=flash_offer.end_time.isoformat() if flash_offer.end_time else None,
            max_quantity=flash_offer.max_quantity,
            remaining_quantity=(
                (flash_offer.max_quantity - flash_offer.used_quantity) 
                if flash_offer.max_quantity else None
            )
        )
    
    def _build_profit_discount_info(self, discount_row: Dict[str, Any]) -> ProfitDiscountInfo:
        """Construye la información de descuento de Profit Plus para incluir en la respuesta."""
        from decimal import Decimal as D
        
        # Construir rangos de descuento
        ranges = []
        for i in range(1, 6):
            hasta_key = f"hasta{i}"
            porc_key = f"porc{i}"
            hasta = discount_row.get(hasta_key)
            porc = discount_row.get(porc_key)
            
            if hasta and porc and D(str(hasta)) > 0 and D(str(porc)) > 0:
                ranges.append({
                    "max_quantity": float(hasta),
                    "discount_percentage": float(porc),
                    "range_number": i
                })
        
        # Determinar mejor descuento y cantidad mínima
        best_discount = None
        min_quantity = None
        if ranges:
            # El mejor descuento es el de mayor porcentaje
            best_range = max(ranges, key=lambda x: x["discount_percentage"])
            best_discount = D(str(best_range["discount_percentage"]))
            # La cantidad mínima es la del primer rango
            min_quantity = D(str(ranges[0]["max_quantity"]))
        
        return ProfitDiscountInfo(
            co_desc=(discount_row.get("co_desc") or "").strip(),
            des_des=discount_row.get("des_des"),
            tip_cli=(discount_row.get("tip_cli") or "").strip(),
            des_tipo=discount_row.get("des_tipo"),
            ranges=ranges,
            fecha_ini=discount_row.get("fecha_ini"),
            fecha_fin=discount_row.get("fecha_fin"),
            is_active=True,  # Ya viene filtrado como activo
            best_discount_percentage=best_discount,
            min_quantity_for_discount=min_quantity
        )

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

    def _load_descriptions(self) -> Dict[str, str]:
        """Carga las descripciones desde el archivo JSON y las mantiene en cache."""
        if self._descriptions_cache is not None:
            return self._descriptions_cache
        
        self._descriptions_cache = {}
        
        if not self._descriptions_file_path.exists():
            self.logger.warning(f"Archivo de descripciones no encontrado: {self._descriptions_file_path}")
            return self._descriptions_cache
        
        try:
            with open(self._descriptions_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            articles = data.get('articles', [])
            for article in articles:
                co_art = (article.get('co_art') or '').strip().upper()
                description = article.get('description', '').strip()
                if co_art and description:
                    self._descriptions_cache[co_art] = description
            
            self.logger.info(f"Cargadas {len(self._descriptions_cache)} descripciones desde JSON")
        except Exception as e:
            self.logger.error(f"Error al cargar descripciones: {str(e)}")
        
        return self._descriptions_cache
    
    def _get_description(self, co_art: str) -> Optional[str]:
        """Obtiene la descripción de un artículo desde el cache."""
        if not co_art:
            return None
        
        descriptions = self._load_descriptions()
        normalized_co_art = co_art.strip().upper()
        return descriptions.get(normalized_co_art)
    
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
        db: Optional[Session] = None,
    ) -> ArticleListResponse:
        """Obtiene el catálogo paginado directamente desde Profit Plus con cache."""
        # Generar clave de cache única basada en todos los parámetros
        cache_key = cache_service._generate_key(
            "catalog",
            page=page,
            limit=limit,
            search=search,
            line_code=line_code,
            category_code=category_code,
            min_price=str(min_price) if min_price is not None else None,
            max_price=str(max_price) if max_price is not None else None,
            sort_by=sort_by,
            price_code=price_code,
            warehouse_code=warehouse_code,
        )
        
        # Intentar obtener del cache
        cached_response = cache_service.get(cache_key)
        if cached_response is not None:
            self.logger.debug(f"Cache hit para catálogo: {cache_key}")
            print(f"✅ CACHE HIT - Catálogo encontrado en cache: {cache_key}")
            print(f"   Productos cacheados: {cached_response.get('total', 0)} artículos en página {cached_response.get('page', 1)}")
            # Convertir el dict de vuelta a ArticleListResponse
            return ArticleListResponse(**cached_response)
        
        self.logger.debug(f"Cache miss para catálogo: {cache_key}")
        print(f"❌ CACHE MISS - Catálogo no encontrado en cache: {cache_key}")
        
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

        article_codes = [(row.get("co_art") or "").strip() for row in result["items"]]
        profit_discounts_map = self._source_service.get_active_discounts_for_articles(
            article_codes=article_codes,
            tip_cli=None  # Por ahora sin filtrar por tipo de cliente
        )
        
        # Obtener imágenes de Cloudinary para todos los artículos en una sola consulta
        cloudinary_images_map = product_image_service.get_main_images_by_articles_batch(
            co_arts=article_codes,
            db=db
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
            
            # image_query = get_image_by_co_art(co_art)
            
            image_url = self._build_image_url(image_guid_normalized)
            
            # Obtener descuento de Profit Plus desde saDescArticulo si existe
            profit_discount = None
            normalized_co_art = co_art.upper().strip()
            profit_discount_row = profit_discounts_map.get(normalized_co_art)
            if profit_discount_row:
                profit_discount = self._build_profit_discount_info(profit_discount_row)
            
            # Obtener descripción desde JSON
            description = self._get_description(co_art)
            
            # Obtener imagen de Cloudinary si existe
            cloudinary_image_url = cloudinary_images_map.get(normalized_co_art)
            
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
                    cloudinary_image_url=cloudinary_image_url,
                    has_cloudinary_image=bool(cloudinary_image_url),
                    description=description,
                    flash_offer=None,  # Ya no se usan flash offers, solo descuentos de Profit Plus
                    profit_discount=profit_discount,
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

        response = ArticleListResponse(
            articles=summaries,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
            filters_applied=filters_applied,
        )
        
        # Almacenar en cache (usar model_dump para Pydantic v2 o dict() para v1)
        try:
            cache_data = response.model_dump() if hasattr(response, 'model_dump') else response.dict()
            cache_service.set(cache_key, cache_data)
            print(f"💾 CACHE SET - Catálogo almacenado en cache: {cache_key}")
            print(f"   Productos almacenados: {response.total} artículos en página {response.page}")
        except Exception as e:
            self.logger.warning(f"Error al almacenar en cache: {e}")
        
        return response

    def get_article_detail(self, co_art: str, db: Optional[Session] = None) -> ArticleDetail:
        """Obtiene el detalle de un artículo y lo transforma a schema con cache."""
        # Normalizar código de artículo
        normalized_co_art = (co_art or "").strip().upper()
        
        # Generar clave de cache
        cache_key = cache_service._generate_key("article", normalized_co_art)
        
        # Intentar obtener del cache
        cached_response = cache_service.get(cache_key)
        if cached_response is not None:
            self.logger.debug(f"Cache hit para detalle de artículo: {normalized_co_art}")
            print(f"✅ CACHE HIT - Detalle de artículo encontrado en cache: {normalized_co_art}")
            
            # IMPORTANTE: Siempre consultar las imágenes de Cloudinary desde la BD,
            # incluso si hay cache, porque las imágenes pueden haber sido agregadas después
            # de que se cacheó la respuesta
            cloudinary_images_raw = product_image_service.get_images_by_article(
                co_art=normalized_co_art,
                db=db
            )
            cloudinary_images = [
                CloudinaryImageInfo(
                    id=img["id"],
                    cloudinary_url=img["cloudinary_url"],
                    cloudinary_public_id=img.get("cloudinary_public_id"),
                    is_main=img.get("is_main", False),
                    display_order=img.get("display_order", 0),
                    description=img.get("description")
                )
                for img in cloudinary_images_raw
            ]
            
            # Actualizar las imágenes de Cloudinary en la respuesta cacheada
            cached_response["cloudinary_images"] = [
                {
                    "id": img["id"],
                    "cloudinary_url": img["cloudinary_url"],
                    "cloudinary_public_id": img.get("cloudinary_public_id"),
                    "is_main": img.get("is_main", False),
                    "display_order": img.get("display_order", 0),
                    "description": img.get("description")
                }
                for img in cloudinary_images_raw
            ]
            
            return ArticleDetail(**cached_response)
        
        self.logger.debug(f"Cache miss para detalle de artículo: {normalized_co_art}")
        print(f"❌ CACHE MISS - Detalle de artículo no encontrado en cache: {normalized_co_art}")
        
        detail = self._source_service.get_article_detail(normalized_co_art)
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

        # Obtener descuento de Profit Plus desde saDescArticulo
        profit_discount = None
        normalized_co_art = (co_art or "").upper().strip()
        
        profit_discounts_map = self._source_service.get_active_discounts_for_articles(
            article_codes=[normalized_co_art],
            tip_cli=None
        )
        profit_discount_row = profit_discounts_map.get(normalized_co_art)
        if profit_discount_row:
            profit_discount = self._build_profit_discount_info(profit_discount_row)

        # Obtener descripción desde JSON
        description = self._get_description(normalized_co_art)
        
        # Obtener imágenes de Cloudinary para este artículo
        # IMPORTANTE: Siempre consultar las imágenes desde la BD, incluso si hay cache
        # porque las imágenes pueden haber sido agregadas después de que se cacheó la respuesta
        cloudinary_images_raw = product_image_service.get_images_by_article(
            co_art=normalized_co_art,
            db=db
        )
        self.logger.debug(f"Imágenes de Cloudinary obtenidas para {normalized_co_art}: {len(cloudinary_images_raw)} imágenes")
        cloudinary_images = [
            CloudinaryImageInfo(
                id=img["id"],
                cloudinary_url=img["cloudinary_url"],
                cloudinary_public_id=img.get("cloudinary_public_id"),
                is_main=img.get("is_main", False),
                display_order=img.get("display_order", 0),
                description=img.get("description")
            )
            for img in cloudinary_images_raw
        ]

        response = ArticleDetail(
            co_art=(header.get("co_art") or "").strip(),
            art_des=header.get("art_des") or "",
            modelo=(header.get("modelo") or "").strip() if header.get("modelo") else None,
            ref=header.get("ref"),
            category_code=(header.get("co_cat") or "").strip() or None,
            category_name=header.get("category_name"),
            line_code=(header.get("co_lin") or "").strip() or None,
            sub_line_code=(header.get("co_subl") or "").strip() or None,
            presentation=None,  # Campo no disponible en saArticulo
            description=description,
            additional_data=additional_data,
            prices=prices,
            stock_by_warehouse=stock,
            images=images,
            cloudinary_images=cloudinary_images,
            flash_offer=None,  # Ya no se usan flash offers, solo descuentos de Profit Plus
            profit_discount=profit_discount,
        )
        
        # Almacenar en cache
        try:
            cache_data = response.model_dump() if hasattr(response, 'model_dump') else response.dict()
            cache_service.set(cache_key, cache_data)
            print(f"💾 CACHE SET - Detalle de artículo almacenado en cache: {normalized_co_art}")
        except Exception as e:
            self.logger.warning(f"Error al almacenar detalle en cache: {e}")
        
        return response

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
        
        # Invalidar cache del artículo ya que cambió su información de imágenes
        normalized_co_art = (co_art or "").strip().upper()
        cache_key = cache_service._generate_key("article", normalized_co_art)
        cache_service.invalidate(cache_key)
        # También invalidar cualquier catálogo que pueda incluir este artículo
        cache_service.invalidate_pattern("catalog:")
        self.logger.info(f"Cache invalidado para artículo {normalized_co_art} después de subir imagen")

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

