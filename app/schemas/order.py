from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from decimal import Decimal

from app.schemas.promotion import QuantityDiscountResponse
from app.schemas.order_discount import OrderDiscountResponse, OrderDiscountSummary

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class PaymentStatusEnum(str, Enum):
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
    """Schema for representing a single item within an order (sistema unificado USD)."""
    id: str
    product_id: str
    quantity: int
    unit_price: Decimal  # USD
    total_price: Decimal  # USD
    selected_presentation: Optional[str] = None
    product_name: str
    product_brand: str
    product_image: Optional[str] = None

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    """Schema for creating a new order from the user's cart (sistema unificado USD)."""
    shipping_address_id: str = Field(..., description="The ID of the user's saved address to ship to.")
    payment_method: str = Field(..., description="The selected payment method (e.g., 'transfer', 'paypal').")
    payment_currency: str = Field(default="USD", description="Moneda del pago: 'USD' o 'VES'")
    payment_capture_url: str = Field(..., description="URL of the payment capture/receipt.")
    customer_notes: Optional[str] = Field(None, description="Optional notes from the customer.")

class OrderResponse(BaseModel):
    """Detailed schema for representing a single order in API responses (sistema unificado USD)."""
    id: str
    user_id: str
    order_number: str
    status: OrderStatus
    subtotal: Decimal  # USD
    shipping_cost: Decimal  # USD
    taxes: Decimal  # USD
    total: Decimal  # USD
    payment_currency: Optional[str] = "USD"  # Moneda en que pagó el usuario
    exchange_rate: Optional[Decimal] = None  # Tasa de cambio si pagó en VES (formateada a 2 decimales)
    payment_method: str
    payment_status: PaymentStatusEnum
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

    # Credit fields (también en USD)
    is_credit_order: bool = False
    credit_amount: Decimal = Decimal('0.00')  # USD
    credit_remaining: Decimal = Decimal('0.00')  # USD
    credit_paid_total: Decimal = Decimal('0.00')  # USD
    payment_due_date: Optional[datetime] = None
    credit_paid: bool = False
    credit_payment_date: Optional[datetime] = None

    # Discount fields
    quantity_discount: Optional[QuantityDiscountResponse] = None
    quantity_discount_amount: Decimal = Decimal('0.00')  # USD
    
    # Complete discount information
    discounts: Optional[OrderDiscountSummary] = None
    original_subtotal: Optional[Decimal] = None  # Subtotal sin descuentos
    total_savings: Decimal = Decimal('0.00')  # Ahorro total en USD

    class Config:
        from_attributes = True

class OrderSummary(BaseModel):
    """A simplified schema for listing multiple orders (sistema unificado USD)."""
    id: str
    order_number: str
    status: OrderStatus
    total: Decimal  # USD
    payment_currency: Optional[str] = "USD"  # Moneda en que pagó
    exchange_rate: Optional[Decimal] = None  # Tasa si pagó en VES
    item_count: int
    created_at: datetime
    
    # Discount information
    total_savings: Decimal = Decimal('0.00')  # Ahorro total en USD
    has_discounts: bool = False  # Si tiene descuentos aplicados

    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    status: str
    
class OrderDashboardResponse(OrderResponse):
    user: str
    
class UpdatePaymentStatus(BaseModel):
    order_id: str
    status: PaymentStatusEnum

class CheckoutPreviewRequest(BaseModel):
    """Schema for checkout preview request."""
    shipping_address_id: str = Field(..., description="The ID of the user's saved address to ship to.")
    payment_currency: str = Field(default="USD", description="Moneda del pago: 'USD' o 'VES'")

class CheckoutPreviewResponse(BaseModel):
    """Schema for checkout preview response with complete cost breakdown."""
    subtotal: Decimal = Field(..., description="Subtotal de productos en USD")
    shipping_cost: Decimal = Field(..., description="Costo de envío en USD")
    taxes: Decimal = Field(..., description="Impuestos (16% IVA) en USD")
    total: Decimal = Field(..., description="Total final en USD")
    payment_currency: str = Field(..., description="Moneda del pago")
    exchange_rate: Optional[Decimal] = Field(None, description="Tasa de cambio si se paga en VES")
    shipping_zone: str = Field(..., description="Zona de envío aplicada")
    shipping_address: OrderAddressSchema = Field(..., description="Dirección de envío")

    # Discount information
    quantity_discount: Optional[QuantityDiscountResponse] = Field(None, description="Descuento por cantidad aplicado")
    quantity_discount_amount: Decimal = Field(Decimal('0.00'), description="Monto del descuento por cantidad en USD")
    flash_discounts: List[dict] = Field(default_factory=list, description="Descuentos flash aplicados")
    total_discount: Decimal = Field(Decimal('0.00'), description="Total de descuentos aplicados en USD")

    class Config:
        from_attributes = True