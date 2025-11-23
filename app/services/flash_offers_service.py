"""
Servicio para manejar la lógica de negocio de Flash Offers
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import HTTPException, status
from decimal import Decimal

from app.models.promotion import FlashOffer, FlashOfferDiscountType
from app.models.product import Product
from app.schemas.promotion import (
    FlashOfferCreate,
    FlashOfferUpdate,
    FlashOfferResponse,
    FlashOfferArticleData,
)
from app.utils.timezone import get_ve_now
from app.services.article_service import ArticleService


class FlashOffersService:
    """Servicio para gestionar flash offers."""
    
    def __init__(self, db: Session, article_service: Optional[ArticleService] = None):
        self.db = db
        self.article_service = article_service or ArticleService()
    
    def create_flash_offer(self, flash_offer_data: FlashOfferCreate) -> FlashOffer:
        """Crear una nueva flash offer."""
        product = None
        if flash_offer_data.product_id:
            product = (
                self.db.query(Product)
                .filter(Product.id == flash_offer_data.product_id)
                .first()
            )
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Producto local no encontrado",
                )
            existing_offers = self.db.query(FlashOffer).filter(
                and_(
                    FlashOffer.product_id == flash_offer_data.product_id,
                    FlashOffer.is_active == True,
                    or_(
                        and_(
                            FlashOffer.start_time <= flash_offer_data.start_time,
                            FlashOffer.end_time >= flash_offer_data.start_time,
                        ),
                        and_(
                            FlashOffer.start_time <= flash_offer_data.end_time,
                            FlashOffer.end_time >= flash_offer_data.end_time,
                        ),
                        and_(
                            FlashOffer.start_time >= flash_offer_data.start_time,
                            FlashOffer.end_time <= flash_offer_data.end_time,
                        ),
                    ),
                )
            ).first()

            if existing_offers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ya existe una flash offer activa para este producto en el rango de fechas especificado",
                )
        
        payload = flash_offer_data.dict()
        fixed_price = payload.pop("fixed_price", None)
        article_code = (payload.get("article_code") or "").strip().upper()
        if not article_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes indicar el código del artículo (co_art) de Profit Plus",
            )
        payload["article_code"] = article_code

        source_price = self._get_source_price(article_code)

        if fixed_price is not None:
            fixed_price_decimal = Decimal(str(fixed_price))
            if fixed_price_decimal <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El precio objetivo debe ser mayor a 0",
                )
            if fixed_price_decimal >= source_price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El precio objetivo debe ser menor al precio del artículo en Profit Plus",
                )
            discount_percentage = ((source_price - fixed_price_decimal) / source_price) * Decimal("100")
            payload["discount_type"] = FlashOfferDiscountType.PERCENTAGE.value
            payload["discount_value"] = float(discount_percentage.quantize(Decimal("0.01")))
        else:
            discount_value = payload.get("discount_value")
            if discount_value is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se pudo determinar el descuento a aplicar",
                )
            payload["discount_type"] = FlashOfferDiscountType.PERCENTAGE.value
            payload["discount_value"] = float(Decimal(str(discount_value)).quantize(Decimal("0.01")))

        flash_offer = FlashOffer(**payload)
        self.db.add(flash_offer)
        self.db.commit()
        self.db.refresh(flash_offer)
        
        return flash_offer
    
    def get_flash_offer(self, offer_id: str) -> Optional[FlashOffer]:
        """Obtener una flash offer por ID."""
        return self.db.query(FlashOffer).filter(FlashOffer.id == offer_id).first()
    
    def get_flash_offers(
        self,
        skip: int = 0,
        limit: int = 10,
        active_only: bool = False,
        valid_only: bool = False,
        product_id: Optional[str] = None,
        article_code: Optional[str] = None,
    ) -> tuple[List[FlashOffer], int]:
        """Obtener lista de flash offers con filtros."""
        query = self.db.query(FlashOffer)
        
        # Aplicar filtros
        if active_only:
            query = query.filter(FlashOffer.is_active == True)
        
        if valid_only:
            now = get_ve_now()
            query = query.filter(
                and_(
                    FlashOffer.is_active == True,
                    FlashOffer.start_time <= now,
                    FlashOffer.end_time >= now
                )
            )
        
        if product_id:
            query = query.filter(FlashOffer.product_id == product_id)

        if article_code:
            query = query.filter(FlashOffer.article_code == article_code.strip().upper())
        
        # Contar total
        total = query.count()
        
        # Aplicar paginación y ordenar por fecha de creación (más recientes primero)
        flash_offers = query.order_by(FlashOffer.created_at.desc()).offset(skip).limit(limit).all()
        
        return flash_offers, total
    
    def update_flash_offer(self, offer_id: str, update_data: FlashOfferUpdate) -> Optional[FlashOffer]:
        """Actualizar una flash offer existente."""
        flash_offer = self.get_flash_offer(offer_id)
        if not flash_offer:
            return None
        
        # Actualizar solo los campos proporcionados
        update_dict = update_data.dict(exclude_unset=True)
        
        # Si se actualizan fechas, verificar conflictos
        if 'start_time' in update_dict or 'end_time' in update_dict:
            new_start = update_dict.get('start_time', flash_offer.start_time)
            new_end = update_dict.get('end_time', flash_offer.end_time)
            
            # Verificar que end_time sea posterior a start_time
            if new_end <= new_start:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La fecha de fin debe ser posterior a la fecha de inicio"
                )
            
            # Verificar conflictos con otras ofertas
            existing_offers = self.db.query(FlashOffer).filter(
                and_(
                    FlashOffer.product_id == flash_offer.product_id,
                    FlashOffer.id != offer_id,
                    FlashOffer.is_active == True,
                    or_(
                        and_(
                            FlashOffer.start_time <= new_start,
                            FlashOffer.end_time >= new_start
                        ),
                        and_(
                            FlashOffer.start_time <= new_end,
                            FlashOffer.end_time >= new_end
                        ),
                        and_(
                            FlashOffer.start_time >= new_start,
                            FlashOffer.end_time <= new_end
                        )
                    )
                )
            ).first()
            
            if existing_offers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Conflicto con otra flash offer activa en el rango de fechas especificado"
                )
        
        # Aplicar actualizaciones
        for field, value in update_dict.items():
            if field == "article_code" and value:
                setattr(flash_offer, field, value.strip().upper())
            else:
                setattr(flash_offer, field, value)
        
        flash_offer.updated_at = get_ve_now()
        self.db.commit()
        self.db.refresh(flash_offer)
        
        return flash_offer

    def _get_source_price(self, article_code: str) -> Decimal:
        """Obtiene el precio actual del producto desde Profit Plus."""
        article_detail = self._fetch_article_detail(article_code)
        price_amount, _ = self._extract_price_info(article_detail)
        return price_amount

    def build_flash_offer_response(self, flash_offer: FlashOffer) -> FlashOfferResponse:
        """Convierte una instancia de FlashOffer en un esquema enriquecido con datos del source."""
        article_details = self._build_article_details(flash_offer)
        base = FlashOfferResponse.model_validate(flash_offer, from_attributes=True)
        return base.model_copy(update={"article_details": article_details})

    def serialize_flash_offers(self, flash_offers: List[FlashOffer]) -> List[FlashOfferResponse]:
        """Enriquece una lista de ofertas con información del source system."""
        return [self.build_flash_offer_response(offer) for offer in flash_offers]

    def _fetch_article_detail(self, article_code: str):
        normalized_code = (article_code or "").strip()
        if not normalized_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El código del artículo (co_art) es obligatorio para las ofertas",
            )
        try:
            return self.article_service.get_article_detail(normalized_code)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"No se pudo obtener el detalle del artículo {normalized_code} en Profit Plus: {exc}",
            ) from exc

    def _extract_price_info(self, article_detail) -> tuple[Decimal, str]:
        price_entry = next((p for p in article_detail.prices if (p.price_code or "").strip() == "01"), None)
        if not price_entry and article_detail.prices:
            price_entry = article_detail.prices[0]

        if not price_entry or price_entry.amount is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El artículo no tiene un precio válido configurado en Profit Plus",
            )

        price_amount = Decimal(str(price_entry.amount))
        if price_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El precio del artículo en Profit Plus debe ser mayor a 0",
            )

        currency = (price_entry.currency or "USD").upper()
        return price_amount, currency

    def _build_article_details(self, flash_offer: FlashOffer) -> FlashOfferArticleData:
        detail = self._fetch_article_detail(flash_offer.article_code)
        original_price, currency = self._extract_price_info(detail)
        discount_percentage = float(flash_offer.discount_value or 0)
        offer_price = (
            original_price
            * (Decimal("100") - Decimal(str(discount_percentage)))
            / Decimal("100")
        ).quantize(Decimal("0.01"))

        gallery = [img.url for img in getattr(detail, "images", []) if getattr(img, "url", None)]
        image_url = gallery[0] if gallery else None

        stock_total = None
        if getattr(detail, "stock_by_warehouse", None):
            stock_total = sum(
                Decimal(str(item.quantity or 0)) for item in detail.stock_by_warehouse
            )

        return FlashOfferArticleData(
            article_code=flash_offer.article_code,
            description=detail.art_des,
            original_price=original_price,
            offer_price=offer_price,
            currency=currency,
            discount_percentage=discount_percentage,
            stock=stock_total,
            image_url=image_url,
            gallery=gallery,
        )
    
    def delete_flash_offer(self, offer_id: str) -> bool:
        """Eliminar una flash offer."""
        flash_offer = self.get_flash_offer(offer_id)
        if not flash_offer:
            return False
        
        self.db.delete(flash_offer)
        self.db.commit()
        return True
    
    def toggle_flash_offer_status(self, offer_id: str) -> Optional[FlashOffer]:
        """Activar/desactivar una flash offer."""
        flash_offer = self.get_flash_offer(offer_id)
        if not flash_offer:
            return None
        
        flash_offer.is_active = not flash_offer.is_active
        flash_offer.updated_at = get_ve_now()
        self.db.commit()
        self.db.refresh(flash_offer)
        
        return flash_offer
    
    def get_active_flash_offers_for_article(self, article_code: str) -> List[FlashOffer]:
        """Obtener todas las flash offers válidas para un artículo específico."""
        now = get_ve_now()
        normalized_code = (article_code or "").strip().upper()
        if not normalized_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debes indicar un código de artículo (co_art) válido",
            )

        return self.db.query(FlashOffer).filter(
            and_(
                FlashOffer.article_code == normalized_code,
                FlashOffer.is_active == True,
                FlashOffer.start_time <= now,
                FlashOffer.end_time >= now,
                or_(
                    FlashOffer.max_quantity.is_(None),
                    FlashOffer.used_quantity < FlashOffer.max_quantity,
                ),
            )
        ).all()
    
    def increment_usage(self, offer_id: str, quantity: int = 1) -> Optional[FlashOffer]:
        """Incrementar el uso de una flash offer."""
        flash_offer = self.get_flash_offer(offer_id)
        if not flash_offer:
            return None
        
        # Verificar que no se exceda la cantidad máxima
        if flash_offer.max_quantity and (flash_offer.used_quantity + quantity) > flash_offer.max_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay suficiente stock disponible para esta oferta"
            )
        
        flash_offer.used_quantity += quantity
        flash_offer.updated_at = get_ve_now()
        self.db.commit()
        self.db.refresh(flash_offer)
        
        return flash_offer
    
    def get_expired_flash_offers(self) -> List[FlashOffer]:
        """Obtener flash offers expiradas."""
        now = get_ve_now()
        return self.db.query(FlashOffer).filter(
            and_(
                FlashOffer.is_active == True,
                FlashOffer.end_time < now
            )
        ).all()
    
    def cleanup_expired_offers(self) -> int:
        """Desactivar automáticamente ofertas expiradas."""
        expired_offers = self.get_expired_flash_offers()
        count = 0
        
        for offer in expired_offers:
            offer.is_active = False
            offer.updated_at = get_ve_now()
            count += 1
        
        if count > 0:
            self.db.commit()
        
        return count
