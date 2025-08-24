from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

class OrderAddressSchema(BaseModel):
    """Schema for the shipping address of an order."""
    street: str = Field(..., description="Street name and number.")
    city: str = Field(..., description="City.")
    state: str = Field(..., description="State or province.")
    postal_code: Optional[str] = Field(None, description="Postal code.")
    country: str = Field("Venezuela", description="Country.")
    recipient_name: str = Field(..., description="Full name of the recipient.")
    recipient_phone: str = Field(..., description="Contact phone number of the recipient.")
    delivery_instructions: Optional[str] = Field(None, description="Special instructions for delivery.")

    class Config:
        from_attributes = True

class OrderItemResponse(BaseModel):
    """Schema for representing a single item within an order."""
    id: str
    product_id: str
    quantity: int
    unit_price: float
    unit_price_ref: float  # Precio unitario en USD/REF
    total_price: float
    total_price_ref: float  # Precio total en USD/REF
    selected_presentation: Optional[str] = None
    product_name: str
    product_brand: str
    product_image: Optional[str] = None

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    """Schema for creating a new order from the user's cart."""
    shipping_address_id: str = Field(..., description="The ID of the user's saved address to ship to.")
    payment_method: str = Field(..., description="The selected payment method (e.g., 'credit_card', 'paypal').")
    payment_capture_url: str = Field(..., description="URL of the payment capture/receipt.")
    customer_notes: Optional[str] = Field(None, description="Optional notes from the customer.")

class OrderResponse(BaseModel):
    """Detailed schema for representing a single order in API responses."""
    id: str
    user_id: str
    order_number: str
    status: OrderStatus
    subtotal: float
    subtotal_ref: float  # Precio en USD/REF
    shipping_cost: float
    shipping_cost_ref: float  # Precio en USD/REF
    taxes: float
    taxes_ref: float  # Precio en USD/REF
    total: float
    total_ref: float  # Precio en USD/REF
    currency: str
    exchange_rate: Optional[float] = None  # Tipo de cambio usado
    payment_method: str
    payment_status: PaymentStatus
    payment_reference: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    customer_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse]
    shipping_address: OrderAddressSchema
    item_count: int
    payment_capture_url: Optional[str] = None

    class Config:
        from_attributes = True

class OrderSummary(BaseModel):
    """A simplified schema for listing multiple orders."""
    id: str
    order_number: str
    status: OrderStatus
    total: float
    total_ref: float  # Precio en USD/REF
    currency: str
    exchange_rate: Optional[float] = None  # Tipo de cambio usado
    item_count: int
    created_at: datetime

    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    status: str
    
class OrderDashboardResponse(OrderResponse):
    user: str
    
class PaymentStatus(BaseModel):
    status: str