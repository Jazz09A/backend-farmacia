import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.models.types import ArrayType
from app.utils.timezone import get_ve_now


class DiscountType(enum.Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"

class FlashOffer(Base):
    __tablename__ = "flash_offers"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Product reference
    product_id = Column(String, ForeignKey("products.id"), nullable=True, index=True)
    
    # Article code from Profit Plus (co_art)
    article_code = Column(String, nullable=False, index=True)

    # Discount configuration
    discount_type = Column(Enum(DiscountType), default=DiscountType.PERCENTAGE, nullable=False)
    discount_value = Column(Float, nullable=False)

    # Time constraints
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)

    # Usage limits
    max_quantity = Column(Integer, nullable=True)
    used_quantity = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)

    # Relationships
    product = relationship("Product", backref="flash_offers")

    def __repr__(self):
        return f"<FlashOffer(id={self.id}, product_id={self.product_id}, discount={self.discount_value})>"

    @property
    def is_valid(self):
        """Check if flash offer is currently valid."""
        now = get_ve_now()
        return (
            self.is_active and
            self.start_time <= now <= self.end_time and
            (self.max_quantity is None or self.used_quantity < self.max_quantity)
        )

    def calculate_discount_amount(self, original_price: float) -> float:
        """Calculate discount amount based on type."""
        if self.discount_type == DiscountType.PERCENTAGE:
            return original_price * (self.discount_value / 100)
        else:
            return min(self.discount_value, original_price)

class PromotionalCode(Base):
    __tablename__ = "promotional_codes"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Code information
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Discount configuration
    discount_type = Column(Enum(DiscountType), default=DiscountType.PERCENTAGE, nullable=False)
    discount_value = Column(Float, nullable=False)

    # Constraints
    min_amount = Column(Float, nullable=True)  # Minimum order amount
    max_discount = Column(Float, nullable=True)  # Maximum discount amount

    # Usage limits
    usage_limit = Column(Integer, nullable=True)  # Total usage limit
    used_count = Column(Integer, default=0)
    user_limit = Column(Integer, default=1)  # Per user limit

    # Time constraints
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)

    # Applicability
    applicable_categories = Column(ArrayType(), nullable=True)  # Category IDs
    applicable_products = Column(ArrayType(), nullable=True)  # Product IDs

    # Status
    is_active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)

    # Relationships
    usages = relationship("PromotionUsage", back_populates="promotional_code", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PromotionalCode(id={self.id}, code={self.code}, discount={self.discount_value})>"

    @property
    def is_valid(self):
        """Check if promotional code is currently valid."""
        now = get_ve_now()
        return (
            self.is_active and
            self.valid_from <= now <= self.valid_until and
            (self.usage_limit is None or self.used_count < self.usage_limit)
        )

    def can_be_used_by_user(self, user_id: str) -> bool:
        """Check if code can be used by specific user."""
        if not self.is_valid:
            return False

        user_usage_count = len([u for u in self.usages if u.user_id == user_id])
        return user_usage_count < self.user_limit

    def calculate_discount(self, order_amount: float, applicable_amount: float | None = None) -> float:
        """Calculate discount amount for given order."""
        if applicable_amount is None:
            applicable_amount = order_amount

        if self.min_amount and order_amount < self.min_amount:
            return 0

        if self.discount_type == DiscountType.PERCENTAGE:
            discount = applicable_amount * (self.discount_value / 100)
        else:
            discount = self.discount_value

        if self.max_discount:
            discount = min(discount, self.max_discount)

        return discount

class PromotionUsage(Base):
    __tablename__ = "promotion_usages"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # References
    promotional_code_id = Column(String, ForeignKey("promotional_codes.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    # order_id eliminado - Order no se usa con Profit Plus
    # order_id = Column(String, ForeignKey("orders.id"), nullable=True, index=True)
    order_id = Column(String, nullable=True, index=True)  # Temporal: mantener para migración (sin FK)

    # Usage details
    discount_amount = Column(Float, nullable=False)
    order_amount = Column(Float, nullable=False)

    # Timestamps
    used_at = Column(DateTime, default=get_ve_now)

    # Relationships
    promotional_code = relationship("PromotionalCode", back_populates="usages")
    user = relationship("User", backref="promotion_usages")
    # order relationship eliminado - Order no se usa con Profit Plus
    # order = relationship("Order", backref="promotion_usage")

    def __repr__(self):
        return f"<PromotionUsage(id={self.id}, code_id={self.promotional_code_id}, user_id={self.user_id})>"

class QuantityDiscount(Base):
    """Modelo para descuentos automáticos basados en cantidad total de productos."""
    __tablename__ = "quantity_discounts"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Configuration
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Quantity range
    min_quantity = Column(Integer, nullable=False)
    max_quantity = Column(Integer, nullable=True)  # None = sin límite superior

    # Discount configuration
    discount_type = Column(Enum(DiscountType), default=DiscountType.PERCENTAGE, nullable=False)
    discount_value = Column(Float, nullable=False)

    # Status and priority
    is_active = Column(Boolean, default=True, index=True)
    priority = Column(Integer, default=0)  # Para ordenar aplicación de descuentos

    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)

    def __repr__(self):
        return f"<QuantityDiscount(id={self.id}, name={self.name}, min_qty={self.min_quantity}, discount={self.discount_value})>"

    def is_applicable(self, total_quantity: int) -> bool:
        """Check if this discount applies to the given quantity."""
        if total_quantity < self.min_quantity:
            return False
        return not (self.max_quantity and total_quantity > self.max_quantity)

    def calculate_discount(self, total_quantity: int, total_amount: float) -> float:
        """Calculate discount amount for given quantity and amount."""
        if not self.is_applicable(total_quantity):
            return 0.0

        if self.discount_type == DiscountType.PERCENTAGE:
            return total_amount * (self.discount_value / 100)
        else:
            return min(self.discount_value, total_amount)

# Legacy Promotion class for backward compatibility
class Promotion(FlashOffer):
    """Legacy promotion class - inherits from FlashOffer for backward compatibility."""
