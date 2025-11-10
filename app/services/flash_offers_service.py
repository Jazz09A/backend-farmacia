"""
Servicio para manejar la lógica de negocio de Flash Offers
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import HTTPException, status

from app.models.promotion import FlashOffer
from app.models.product import Product
from app.schemas.promotion import FlashOfferCreate, FlashOfferUpdate
from app.utils.timezone import get_ve_now


class FlashOffersService:
    """Servicio para gestionar flash offers."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_flash_offer(self, flash_offer_data: FlashOfferCreate) -> FlashOffer:
        """Crear una nueva flash offer."""
        # Verificar que el producto existe
        product = self.db.query(Product).filter(Product.id == flash_offer_data.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado"
            )
        
        # Verificar que no haya conflictos de tiempo con otras ofertas del mismo producto
        existing_offers = self.db.query(FlashOffer).filter(
            and_(
                FlashOffer.product_id == flash_offer_data.product_id,
                FlashOffer.is_active == True,
                or_(
                    and_(
                        FlashOffer.start_time <= flash_offer_data.start_time,
                        FlashOffer.end_time >= flash_offer_data.start_time
                    ),
                    and_(
                        FlashOffer.start_time <= flash_offer_data.end_time,
                        FlashOffer.end_time >= flash_offer_data.end_time
                    ),
                    and_(
                        FlashOffer.start_time >= flash_offer_data.start_time,
                        FlashOffer.end_time <= flash_offer_data.end_time
                    )
                )
            )
        ).first()
        
        if existing_offers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe una flash offer activa para este producto en el rango de fechas especificado"
            )
        
        # Crear la flash offer
        flash_offer = FlashOffer(**flash_offer_data.dict())
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
        product_id: Optional[str] = None
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
            setattr(flash_offer, field, value)
        
        flash_offer.updated_at = get_ve_now()
        self.db.commit()
        self.db.refresh(flash_offer)
        
        return flash_offer
    
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
    
    def get_active_flash_offers_for_product(self, product_id: str) -> List[FlashOffer]:
        """Obtener todas las flash offers válidas para un producto."""
        now = get_ve_now()
        return self.db.query(FlashOffer).filter(
            and_(
                FlashOffer.product_id == product_id,
                FlashOffer.is_active == True,
                FlashOffer.start_time <= now,
                FlashOffer.end_time >= now,
                or_(
                    FlashOffer.max_quantity.is_(None),
                    FlashOffer.used_quantity < FlashOffer.max_quantity
                )
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
