"""
Servicio para manejar la lógica de negocio de descuentos
"""
from typing import List, Optional, Dict
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_

from app.models.promotion import QuantityDiscount, FlashOffer, DiscountType
from app.models.cart import CartItem
from app.models.product import Product
from app.utils.timezone import get_ve_now


class DiscountService:
    """Servicio para gestionar descuentos y promociones."""

    def __init__(self, db: Session):
        self.db = db

    def get_applicable_quantity_discount(self, total_quantity: int) -> Optional[QuantityDiscount]:
        """Obtener descuento por cantidad aplicable."""
        return self.db.query(QuantityDiscount).filter(
            and_(
                QuantityDiscount.is_active == True,
                QuantityDiscount.min_quantity <= total_quantity,
                or_(
                    QuantityDiscount.max_quantity.is_(None),
                    QuantityDiscount.max_quantity >= total_quantity
                )
            )
        ).order_by(QuantityDiscount.priority.desc()).first()

    def get_active_flash_offers_for_products(self, product_ids: List[str]) -> Dict[str, FlashOffer]:
        """Obtener ofertas flash activas para una lista de productos."""
        now = get_ve_now()
        flash_offers = self.db.query(FlashOffer).filter(
            and_(
                FlashOffer.product_id.in_(product_ids),
                FlashOffer.is_active == True,
                FlashOffer.start_time <= now,
                FlashOffer.end_time >= now,
                or_(
                    FlashOffer.max_quantity.is_(None),
                    FlashOffer.used_quantity < FlashOffer.max_quantity
                )
            )
        ).all()

        return {offer.product_id: offer for offer in flash_offers}

    def calculate_cart_discounts(self, cart_items: List[CartItem]) -> Dict:
        """
        Calcular todos los descuentos aplicables al carrito.

        Returns:
            dict con información completa de descuentos aplicables
        """
        if not cart_items:
            return {
                "quantity_discount": None,
                "quantity_discount_amount": Decimal('0.00'),
                "flash_discounts": {},
                "flash_discount_total": Decimal('0.00'),
                "total_discount": Decimal('0.00'),
                "subtotal_after_discounts": Decimal('0.00')
            }

        # Calcular totales base
        total_quantity = sum(item.quantity for item in cart_items)
        subtotal = Decimal('0.00')

        for item in cart_items:
            subtotal += item.product.price * item.quantity

        # Obtener descuento por cantidad
        quantity_discount = self.get_applicable_quantity_discount(total_quantity)
        quantity_discount_amount = Decimal('0.00')

        if quantity_discount:
            quantity_discount_amount = Decimal(str(quantity_discount.calculate_discount(total_quantity, float(subtotal))))

        # Obtener ofertas flash activas
        product_ids = [item.product_id for item in cart_items]
        flash_offers = self.get_active_flash_offers_for_products(product_ids)

        # Calcular descuentos por flash offers
        flash_discounts = {}
        flash_discount_total = Decimal('0.00')

        for item in cart_items:
            if item.product_id in flash_offers:
                offer = flash_offers[item.product_id]
                discount_per_item = Decimal(str(offer.calculate_discount_amount(float(item.product.price))))
                total_discount_for_item = discount_per_item * item.quantity
                flash_discounts[item.product_id] = total_discount_for_item
                flash_discount_total += total_discount_for_item

        # Calcular subtotal después de descuentos
        subtotal_after_discounts = subtotal - quantity_discount_amount - flash_discount_total

        return {
            "subtotal_original": subtotal,  # Subtotal sin descuentos
            "quantity_discount": quantity_discount,
            "quantity_discount_amount": quantity_discount_amount,
            "flash_discounts": flash_discounts,
            "flash_discount_total": flash_discount_total,
            "total_discount": quantity_discount_amount + flash_discount_total,
            "subtotal_after_discounts": subtotal_after_discounts
        }

    def create_quantity_discount(self, discount_data: Dict) -> QuantityDiscount:
        """Crear un nuevo descuento por cantidad."""
        discount = QuantityDiscount(**discount_data)
        self.db.add(discount)
        self.db.commit()
        self.db.refresh(discount)
        return discount

    def get_quantity_discounts(self, skip: int = 0, limit: int = 10, active_only: bool = False) -> tuple[List[QuantityDiscount], int]:
        """Obtener lista de descuentos por cantidad con paginación."""
        query = self.db.query(QuantityDiscount)

        if active_only:
            query = query.filter(QuantityDiscount.is_active == True)

        total = query.count()
        discounts = query.order_by(QuantityDiscount.priority.desc(), QuantityDiscount.created_at.desc()).offset(skip).limit(limit).all()

        return discounts, total

    def get_quantity_discount(self, discount_id: str) -> Optional[QuantityDiscount]:
        """Obtener un descuento por cantidad por ID."""
        return self.db.query(QuantityDiscount).filter(QuantityDiscount.id == discount_id).first()

    def update_quantity_discount(self, discount_id: str, update_data: Dict) -> Optional[QuantityDiscount]:
        """Actualizar un descuento por cantidad."""
        discount = self.get_quantity_discount(discount_id)
        if not discount:
            return None

        for field, value in update_data.items():
            if hasattr(discount, field):
                setattr(discount, field, value)

        discount.updated_at = None  # Trigger onupdate
        self.db.commit()
        self.db.refresh(discount)
        return discount

    def delete_quantity_discount(self, discount_id: str) -> bool:
        """Eliminar un descuento por cantidad."""
        discount = self.get_quantity_discount(discount_id)
        if not discount:
            return False

        self.db.delete(discount)
        self.db.commit()
        return True

    def toggle_quantity_discount_status(self, discount_id: str) -> Optional[QuantityDiscount]:
        """Activar/desactivar un descuento por cantidad."""
        discount = self.get_quantity_discount(discount_id)
        if not discount:
            return None

        discount.is_active = not discount.is_active
        discount.updated_at = None  # Trigger onupdate
        self.db.commit()
        self.db.refresh(discount)
        return discount