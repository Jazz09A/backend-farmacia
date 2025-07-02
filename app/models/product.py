from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import TypeDecorator, JSON
from app.config.database import Base
import uuid
from datetime import datetime
import json

# Custom array type that works with both SQLite and PostgreSQL
class ArrayType(TypeDecorator):
    """Custom type that stores arrays as JSON in SQLite and as ARRAY in PostgreSQL"""
    
    impl = JSON
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(ARRAY(String))
        else:
            return dialect.type_descriptor(JSON())
    
    def process_bind_param(self, value, dialect):
        if dialect.name == 'postgresql':
            return value
        else:
            # For SQLite, store as JSON string
            if value is None:
                return None
            return json.dumps(value) if isinstance(value, list) else value
    
    def process_result_value(self, value, dialect):
        if dialect.name == 'postgresql':
            return value
        else:
            # For SQLite, parse from JSON string
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return []
            return value if isinstance(value, list) else []

class Product(Base):
    __tablename__ = "products"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Basic product information
    name = Column(String, nullable=False, index=True)
    slug = Column(String, unique=True, nullable=True, index=True)
    sku = Column(String, unique=True, nullable=True)
    
    # Foreign key references
    brand_id = Column(String, ForeignKey("brands.id"), nullable=True, index=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=True, index=True)
    
    # Legacy fields for backward compatibility
    brand = Column(String, nullable=True, index=True)  # Legacy field
    category = Column(String, nullable=True, index=True)  # Legacy field
    subcategory = Column(String, nullable=True, index=True)
    patology = Column(String, nullable=True, index=True)
    
    # Pricing
    price_ves = Column(Float, nullable=False)
    price_ref = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)  # For offers
    
    # Description and details
    description = Column(Text, nullable=False)
    ingredients = Column(ArrayType(), nullable=True)  # Now compatible with SQLite
    
    # Images
    image = Column(String, nullable=False)  # Main image
    images = Column(ArrayType(), nullable=True)  # Now compatible with SQLite
    
    # Stock management
    in_stock = Column(Boolean, default=True, index=True)
    stock = Column(Integer, default=0)
    
    # Prescription requirement
    prescription = Column(Boolean, default=False, index=True)
    
    # Rating and reviews
    rating = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)
    
    # Offers and promotions
    is_offer = Column(Boolean, default=False, index=True)
    offer_end_time = Column(DateTime, nullable=True)
    
    # Featured products
    featured = Column(Boolean, default=False, index=True)
    
    # Medical information
    dosage = Column(String, nullable=True)
    presentation = Column(String, nullable=True)
    laboratorio = Column(String, nullable=True)
    registro_sanitario = Column(String, nullable=True)
    contraindicaciones = Column(Text, nullable=True)
    efectos_secundarios = Column(Text, nullable=True)
    
    # SEO and URL
    slug = Column(String, unique=True, nullable=True, index=True)
    meta_title = Column(String, nullable=True)
    meta_description = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    brand_obj = relationship("Brand", back_populates="products")
    category_obj = relationship("Category", back_populates="products")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")
    cart_items = relationship("CartItem", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")
    favorited_by = relationship("UserFavorite", back_populates="product", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, brand={self.brand})>"
    
    @property
    def current_price(self):
        """Return current price (offer price if available, otherwise regular price)."""
        if self.is_offer and self.original_price:
            return self.price_ves
        return self.price_ves
    
    @property
    def discount_percentage(self):
        """Calculate discount percentage if product is on offer."""
        if self.is_offer and self.original_price and self.original_price > 0:
            return round(((self.original_price - self.price_ves) / self.original_price) * 100, 2)
        return 0
    
    @property
    def is_available(self):
        """Check if product is available (in stock and active)."""
        return self.in_stock and self.stock > 0
    
    def update_rating(self, new_rating: float, is_new_review: bool = True):
        """Update product rating based on new review."""
        if is_new_review:
            total_rating = (self.rating * self.review_count) + new_rating
            self.review_count += 1
            self.rating = round(total_rating / self.review_count, 2)
        else:
            # Recalculate rating from all reviews
            from app.models.review import Review
            from sqlalchemy import func
            # This would need the session to calculate
            pass 