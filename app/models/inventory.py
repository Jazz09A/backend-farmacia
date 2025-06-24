from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from datetime import datetime
import enum

class MovementType(enum.Enum):
    IN = "in"
    OUT = "out"
    ADJUSTMENT = "adjustment"

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Product reference
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    
    # Movement details
    movement_type = Column(Enum(MovementType), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    reason = Column(String(100), nullable=True)
    reference_id = Column(String(255), nullable=True)  # order_id, adjustment_id, etc.
    
    # Cost tracking
    unit_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    
    # Stock before and after
    stock_before = Column(Integer, nullable=False)
    stock_after = Column(Integer, nullable=False)
    
    # User reference
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    product = relationship("Product", backref="inventory_movements")
    user = relationship("User", backref="inventory_movements")
    
    def __repr__(self):
        return f"<InventoryMovement(id={self.id}, product_id={self.product_id}, type={self.movement_type.value}, quantity={self.quantity})>"

class StockAlert(Base):
    __tablename__ = "stock_alerts"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Product reference
    product_id = Column(String, ForeignKey("products.id"), nullable=False, unique=True, index=True)
    
    # Alert configuration
    min_stock_threshold = Column(Integer, nullable=False, default=5)
    max_stock_threshold = Column(Integer, nullable=False, default=1000)
    
    # Alert status
    is_low_stock = Column(Boolean, default=False, index=True)
    is_out_of_stock = Column(Boolean, default=False, index=True)
    is_overstocked = Column(Boolean, default=False, index=True)
    
    # Notifications
    low_stock_notified = Column(Boolean, default=False)
    out_of_stock_notified = Column(Boolean, default=False)
    overstocked_notified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_check = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    product = relationship("Product", backref="stock_alert")
    
    def __repr__(self):
        return f"<StockAlert(id={self.id}, product_id={self.product_id}, min_threshold={self.min_stock_threshold})>"
    
    def check_stock_levels(self, current_stock: int):
        """Update alert status based on current stock."""
        self.is_out_of_stock = current_stock == 0
        self.is_low_stock = 0 < current_stock <= self.min_stock_threshold
        self.is_overstocked = current_stock > self.max_stock_threshold
        self.last_check = datetime.utcnow()

class BatchTracking(Base):
    __tablename__ = "batch_tracking"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Product reference
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    
    # Batch details
    batch_number = Column(String(100), nullable=False, index=True)
    manufacture_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    
    # Quantities
    initial_quantity = Column(Integer, nullable=False)
    current_quantity = Column(Integer, nullable=False)
    reserved_quantity = Column(Integer, default=0)
    
    # Cost and pricing
    unit_cost = Column(Float, nullable=True)
    selling_price = Column(Float, nullable=True)
    
    # Supplier information
    supplier_name = Column(String(255), nullable=True)
    supplier_invoice = Column(String(100), nullable=True)
    
    # Quality control
    quality_checked = Column(Boolean, default=False)
    quality_status = Column(String(50), nullable=True)  # approved, rejected, pending
    quality_notes = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    product = relationship("Product", backref="batches")
    
    def __repr__(self):
        return f"<BatchTracking(id={self.id}, batch_number={self.batch_number}, product_id={self.product_id})>"
    
    @property
    def available_quantity(self):
        """Return available quantity (current - reserved)."""
        return self.current_quantity - self.reserved_quantity
    
    @property
    def is_expired(self):
        """Check if batch is expired."""
        if not self.expiry_date:
            return False
        return datetime.utcnow() > self.expiry_date
    
    @property
    def days_to_expiry(self):
        """Return days until expiry."""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - datetime.utcnow()
        return delta.days if delta.days > 0 else 0 