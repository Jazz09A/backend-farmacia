"""
Modelo para descuentos aplicados en órdenes
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, Numeric
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from datetime import datetime
from enum import Enum as PyEnum

class DiscountType(PyEnum):
    """Tipos de descuentos aplicables a órdenes"""
    QUANTITY = "quantity"
    FLASH = "flash"
    COUPON = "coupon"
    PROMOTIONAL = "promotional"

class OrderDiscount(Base):
    """Modelo para descuentos aplicados en órdenes específicas."""
    __tablename__ = "order_discounts"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Order reference
    order_id = Column(String, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    # Discount information
    discount_type = Column(Enum(DiscountType), nullable=False, index=True)
    discount_id = Column(String, nullable=True)  # ID del descuento original (quantity_discount, flash_offer, etc.)
    discount_name = Column(String, nullable=False)  # Nombre descriptivo del descuento
    discount_description = Column(Text, nullable=True)  # Descripción del descuento

    # Discount calculation
    discount_value = Column(Numeric(10, 2), nullable=False)  # Valor del descuento (porcentaje o monto fijo)
    discount_amount = Column(Numeric(10, 2), nullable=False)  # Monto real descontado en USD
    applied_to = Column(String, nullable=False, default="subtotal")  # A qué se aplicó: subtotal, shipping, total

    # Additional context
    product_id = Column(String, nullable=True)  # Para descuentos específicos de producto
    quantity_threshold = Column(String, nullable=True)  # Para descuentos por cantidad (ej: "50+")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    order = relationship("Order", back_populates="discounts")

    def __repr__(self):
        return f"<OrderDiscount(id={self.id}, order_id={self.order_id}, type={self.discount_type}, amount={self.discount_amount})>"

    @property
    def formatted_discount(self):
        """Formato legible del descuento para mostrar al usuario"""
        if self.discount_type == DiscountType.QUANTITY:
            return f"{self.discount_name} ({self.quantity_threshold or ''})"
        elif self.discount_type == DiscountType.FLASH:
            return f"Oferta Flash: {self.discount_name}"
        elif self.discount_type == DiscountType.COUPON:
            return f"Cupón: {self.discount_name}"
        else:
            return self.discount_name
