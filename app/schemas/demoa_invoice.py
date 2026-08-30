"""
Schemas para facturas y pagos de DEMOA
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DEMOAInvoiceResponse(BaseModel):
    """Respuesta de factura DEMOA"""
    invoice_number: str
    emission_date: datetime
    due_date: datetime | None = None
    total_amount: Decimal
    balance: Decimal
    amount_paid: Decimal
    currency: str
    status: str  # 'pending', 'paid'
    order_status: str  # 'active', 'processing', 'requires_attention'
    is_printed: bool
    
    class Config:
        from_attributes = True


class DEMOAInvoiceItem(BaseModel):
    """Item de una factura (sin exponer código de producto)"""
    line_number: int
    product_name: str
    product_barcode: str | None = None
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal
    
    class Config:
        from_attributes = True


class DEMOAInvoiceDetails(DEMOAInvoiceResponse):
    """Detalles completos de factura con items"""
    items: list[DEMOAInvoiceItem]
    
    class Config:
        from_attributes = True


class DEMOAPaymentResponse(BaseModel):
    """Información de pago"""
    payment_number: str
    payment_date: datetime
    total_payment_amount: Decimal
    invoice_number: str
    amount_applied: Decimal
    
    class Config:
        from_attributes = True


class DEMOAInvoiceSummary(BaseModel):
    """Resumen de facturas del cliente"""
    total_invoices: int
    pending_invoices: int
    paid_invoices: int
    total_pending_amount: Decimal
    total_invoiced: Decimal
    
    class Config:
        from_attributes = True

