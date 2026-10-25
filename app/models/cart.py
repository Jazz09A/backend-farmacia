import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.utils.timezone import get_ve_now


class CartItem(Base):
    __tablename__ = "cart_items"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # References
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)

    # Item details
    quantity = Column(Integer, nullable=False, default=1)
    selected_presentation = Column(String, nullable=True)  # If product has multiple presentations

    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)

    # Relationships
    user = relationship("User", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")

    # Índices compuestos para optimizar detección de duplicados y listado por usuario
    __table_args__ = (Index("idx_cart_user_product_pres", "user_id", "product_id", "selected_presentation"),)

    def __repr__(self):
        return (
            f"<CartItem(id={self.id}, user_id={self.user_id}, product_id={self.product_id}, quantity={self.quantity})>"
        )

    @property
    def total_price(self):
        """Calculate total price for this cart item."""
        if self.product:
            return self.product.current_price * self.quantity
        return 0.0

    @property
    def unit_price(self):
        """Get unit price of the product."""
        if self.product:
            return self.product.current_price
        return 0.0
