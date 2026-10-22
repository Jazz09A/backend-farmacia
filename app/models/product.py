import json
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.config.database import Base
from app.utils.timezone import get_ve_now


# Custom array type that works with both SQLite and PostgreSQL
class ArrayType(TypeDecorator):
    """Custom type that stores arrays as JSON in SQLite and as ARRAY in PostgreSQL"""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        else:
            return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite, store as JSON string
            if value is None:
                return None
            return json.dumps(value) if isinstance(value, list) else value

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite, parse from JSON string
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass

            return value if isinstance(value, list) else []


class Product(Base):  # type: ignore[valid-type, misc]
    __tablename__ = "products"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Basic product information
    name = Column(String, nullable=False, index=True)
    slug = Column(String, unique=True, nullable=True, index=True)
    sku = Column(String, unique=True, nullable=True, index=True)

    # Foreign key references
    brand_id = Column(String, ForeignKey("brands.id"), nullable=True, index=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=True, index=True)

    # Legacy fields for backward compatibility
    brand = Column(String, nullable=True, index=True)  # Legacy field
    category = Column(String, nullable=True, index=True)  # Legacy field
    subcategory = Column(String, nullable=True, index=True)

    # Pricing (USD only - sistema unificado)
    price = Column(Numeric(10, 2), nullable=False, index=True)  # Precio base en USD
    original_price = Column(Numeric(10, 2), nullable=True)  # Precio original en USD para ofertas

    # Description and details
    description = Column(Text, nullable=False)
    ingredients = Column(ArrayType(), nullable=True)  # Now compatible with SQLite

    # Images
    image = Column(String, nullable=False)  # Main image
    images = Column(ArrayType(), nullable=True)  # Now compatible with SQLite

    # Stock management
    in_stock = Column(Boolean, default=True, index=True)
    stock = Column(Integer, default=0, index=True)  # Add index for stock filtering

    # Prescription requirement
    prescription = Column(Boolean, default=False, index=True)

    # Rating and reviews
    rating = Column(Numeric(3, 2), default=Decimal("0.00"), index=True)  # Add index for rating sorting

    # Offers and promotions
    is_offer = Column(Boolean, default=False, index=True)

    # Featured products
    featured = Column(Boolean, default=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=get_ve_now, index=True)  # Add index for date sorting
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)

    # Relationships
    cart_items = relationship("CartItem", back_populates="product")
    # order_items relationship eliminado - Order no se usa con Profit Plus
    # order_items = relationship("OrderItem", back_populates="product")
    favorited_by = relationship("UserFavorite", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, brand={self.brand})>"

    @property
    def current_price(self):
        """Return current price in USD (offer price if available, otherwise regular price)."""
        if self.is_offer and self.original_price:
            return self.price  # Precio de oferta en USD
        return self.price  # Precio regular en USD

    @property
    def discount_percentage(self):
        """Calculate discount percentage if product is on offer (based on USD prices)."""
        if self.is_offer and self.original_price and self.original_price > 0:
            return round(((self.original_price - self.price) / self.original_price) * 100, 2)
        return 0

    @property
    def is_available(self):
        """Check if product is available based on stock."""
        return self.in_stock and self.stock > 0

    # Add compound indexes for common query patterns
    __table_args__ = (
        # Index for filtering products in stock with category
        Index("idx_product_stock_category", "in_stock", "category_id"),
        # Index for filtering products in stock with brand
        Index("idx_product_stock_brand", "in_stock", "brand_id"),
        # Index for featured products that are in stock
        Index("idx_product_featured_stock", "featured", "in_stock"),
        # Index for offers that are in stock
        Index("idx_product_offer_stock", "is_offer", "in_stock"),
        # Index for prescription filtering with stock
        Index("idx_product_prescription_stock", "prescription", "in_stock"),
        # Index for price range queries with stock
        Index("idx_product_price_stock", "price", "in_stock"),
        # Index for sorting by rating with stock
        Index("idx_product_rating_stock", "rating", "in_stock"),
        # Index for sorting by creation date
        Index("idx_product_created_stock", "created_at", "in_stock"),
    )
