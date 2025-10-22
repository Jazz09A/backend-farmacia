from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from decimal import Decimal

class CreditInfo(BaseModel):
    """Información de crédito del usuario"""
    available_credit: Decimal
    credit_limit: Decimal
    credit_status: str

class CreditPaymentCreate(BaseModel):
    """Crear un pago parcial (sistema unificado USD)"""
    order_id: str = Field(..., description="ID de la orden")
    amount: Decimal = Field(..., gt=0, description="Monto del pago")
    payment_currency: str = Field(default="USD", description="Moneda del pago: 'USD' o 'VES'")
    payment_reference: str = Field(..., min_length=1, description="Referencia del pago")
    payment_capture_url: Optional[str] = Field(None, description="URL de la captura del pago")

class CreditPaymentResponse(BaseModel):
    """Respuesta de pago de crédito (sistema unificado USD)"""
    id: str
    order_id: str
    amount: Decimal  # Monto en USD (después de conversión si era VES)
    payment_currency: str  # Moneda en que pagó el usuario ('USD' o 'VES')
    exchange_rate_used: Optional[Decimal] = None  # Tasa usada si pagó en VES
    payment_reference: str
    payment_capture_url: Optional[str] = None
    status: str
    created_at: datetime
    approved_at: Optional[datetime] = None
    admin_notes: Optional[str] = None

    class Config:
        from_attributes = True

class PaymentApproval(BaseModel):
    """Aprobar o rechazar un pago"""
    payment_id: str
    action: str = Field(..., pattern="^(approve|reject)$", description="Acción: approve o reject")
    admin_notes: Optional[str] = Field(None, description="Notas del administrador")

class CreditOrderCreate(BaseModel):
    """Crear orden con crédito"""
    shipping_address_id: str = Field(..., description="ID de la dirección de envío")
    payment_due_days: int = Field(30, ge=1, le=365, description="Días para pagar")
    customer_notes: Optional[str] = Field(None, description="Notas del cliente")

class CreditDashboard(BaseModel):
    """Dashboard de crédito para usuario"""
    user_credit: CreditInfo
    orders: dict
    payments: dict

class AdminCreditDashboard(BaseModel):
    """Dashboard de crédito para admin"""
    pending_payments: int
    approved_today: int
    total_pending_amount: Decimal
    orders_with_pending: int

class PaymentDetails(BaseModel):
    """Detalles completos de un pago"""
    payment: CreditPaymentResponse
    order: dict
    user: dict

class CreditOrderItem(BaseModel):
    """Item de una orden con crédito (sistema unificado USD)"""
    id: str
    product_id: str
    product_name: str
    product_brand: str
    product_image: Optional[str] = None
    quantity: int
    unit_price: Decimal  # USD
    total_price: Decimal  # USD
    selected_presentation: Optional[str] = None
    
    class Config:
        from_attributes = True

class CreditOrderAddress(BaseModel):
    """Dirección de envío de una orden con crédito"""
    street: str
    city: str
    state: str
    postal_code: Optional[str] = None
    country: str
    recipient_name: str
    recipient_phone: str
    delivery_instructions: Optional[str] = None
    
    class Config:
        from_attributes = True

class CreditOrderResponse(BaseModel):
    """Respuesta completa de una orden con crédito (sistema unificado USD)"""
    id: str
    order_number: str
    status: str
    total: Decimal  # USD
    payment_currency: Optional[str] = "USD"  # Moneda en que pagó
    exchange_rate: Optional[Decimal] = None  # Tasa si pagó en VES
    created_at: datetime
    updated_at: datetime
    
    # Información específica de crédito (todo en USD)
    credit_amount: Decimal  # USD
    credit_remaining: Decimal  # USD
    credit_paid_total: Decimal  # USD
    payment_due_date: Optional[datetime] = None
    credit_paid: bool
    credit_payment_date: Optional[datetime] = None
    
    # Información de pago
    payment_status: str
    payment_method: str
    
    # Items de la orden
    items: List[CreditOrderItem]
    
    # Dirección de envío
    shipping_address: Optional[CreditOrderAddress] = None
    
    # Pagos realizados
    credit_payments: List[CreditPaymentResponse]
    
    # Información adicional
    item_count: int
    customer_notes: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    class Config:
        from_attributes = True