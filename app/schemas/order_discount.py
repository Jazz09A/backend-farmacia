"""
Schemas para descuentos de órdenes
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal
from enum import Enum

class DiscountTypeEnum(str, Enum):
    """Tipos de descuentos aplicables a órdenes"""
    QUANTITY = "quantity"
    FLASH = "flash"
    COUPON = "coupon"
    PROMOTIONAL = "promotional"

class OrderDiscountBase(BaseModel):
    """Schema base para descuentos de órdenes"""
    discount_type: DiscountTypeEnum
    discount_id: Optional[str] = None
    discount_name: str
    discount_description: Optional[str] = None
    discount_value: Decimal = Field(..., description="Valor del descuento (porcentaje o monto fijo)")
    discount_amount: Decimal = Field(..., description="Monto real descontado en USD")
    applied_to: str = Field(default="subtotal", description="A qué se aplicó: subtotal, shipping, total")
    product_id: Optional[str] = None
    quantity_threshold: Optional[str] = None

class OrderDiscountCreate(OrderDiscountBase):
    """Schema para crear un descuento de orden"""
    order_id: str

class OrderDiscountResponse(OrderDiscountBase):
    """Schema para respuesta de descuento de orden"""
    id: str
    order_id: str
    created_at: datetime
    formatted_discount: str = Field(..., description="Formato legible del descuento")

    class Config:
        from_attributes = True

class OrderDiscountSummary(BaseModel):
    """Schema resumido para descuentos de órdenes"""
    total_discounts: int = Field(..., description="Número total de descuentos aplicados")
    total_discount_amount: Decimal = Field(..., description="Monto total descontado en USD")
    discount_breakdown: list[OrderDiscountResponse] = Field(..., description="Desglose de descuentos")
    savings_percentage: float = Field(..., description="Porcentaje de ahorro total")

class OrderWithDiscounts(BaseModel):
    """Schema para órdenes con información de descuentos"""
    order_id: str
    order_number: str
    subtotal: Decimal
    total: Decimal
    discounts: OrderDiscountSummary
    original_subtotal: Decimal = Field(..., description="Subtotal original sin descuentos")
    original_total: Decimal = Field(..., description="Total original sin descuentos")
    total_savings: Decimal = Field(..., description="Ahorro total en USD")
