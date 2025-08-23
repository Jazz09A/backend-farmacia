from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from datetime import datetime, timezone
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class Order(Base):
    __tablename__ = "orders"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # User reference
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Order information
    order_number = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, nullable=False, default=OrderStatus.PENDING.value, index=True)
    # Status options: received, confirmed, preparing, shipping, delivered, cancelled
    
    # Pricing
    subtotal = Column(Float, nullable=False)
    shipping_cost = Column(Float, nullable=False)
    taxes = Column(Float, nullable=False)
    total = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default='VES')
    
    # Payment information
    payment_method = Column(String, nullable=False)
    payment_status = Column(String, default=OrderStatus.PENDING.value)
    # Payment status: pending, processing, completed, failed, refunded
    payment_reference = Column(String, nullable=True)
    payment_capture_url = Column(String, nullable=True)  # URL to the payment receipt image/capture
    payment_details = Column(Text, nullable=True)  # JSON string with additional payment info
    
    # Shipping information
    tracking_number = Column(String, nullable=True, index=True)
    estimated_delivery = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    
    # Notes and additional information
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    shipping_address = relationship("OrderAddress", back_populates="order", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Order(id={self.id}, order_number={self.order_number}, status={self.status})>"
    
    @property
    def item_count(self):
        """Total number of items in the order."""
        return sum(item.quantity for item in self.items)
    
    @property
    def can_be_cancelled(self):
        """Check if order can be cancelled."""
        return self.status in ['received', 'confirmed']
    
    def generate_order_number(self):
        """Generate a unique order number."""
        import random
        import string
        timestamp = datetime.now().strftime("%Y%m%d")
        random_suffix = ''.join(random.choices(string.digits, k=4))
        return f"FP{timestamp}{random_suffix}"

class OrderItem(Base):
    __tablename__ = "order_items"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # References
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    
    # Item details
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    selected_presentation = Column(String, nullable=True)
    
    # Product snapshot (in case product changes)
    product_name = Column(String, nullable=False)
    product_brand = Column(String, nullable=False)
    product_image = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    
    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
    
    def __repr__(self):
        return f"<OrderItem(id={self.id}, product={self.product_name}, quantity={self.quantity})>"

class OrderAddress(Base):
    __tablename__ = "order_addresses"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Order reference
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, unique=True)
    
    # Address information
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    postal_code = Column(String, nullable=True)
    country = Column(String, nullable=False, default='Venezuela')
    
    # Contact information
    recipient_name = Column(String, nullable=False)
    recipient_phone = Column(String, nullable=False)
    
    # Additional details
    address_type = Column(String, nullable=True)  # home, office, etc.
    delivery_instructions = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    
    # Relationships
    order = relationship("Order", back_populates="shipping_address")
    
    def __repr__(self):
        return f"<OrderAddress(id={self.id}, city={self.city}, recipient={self.recipient_name})>"
    
    @property
    def full_address(self):
        """Return formatted full address."""
        parts = [self.street, self.city, self.state]
        if self.postal_code:
            parts.append(self.postal_code)
        parts.append(self.country)
        return ", ".join(parts) 