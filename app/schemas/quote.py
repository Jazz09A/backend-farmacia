from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class QuoteItem(BaseModel):
    line_number: int = Field(..., ge=1)
    product_code: str
    product_name: Optional[str] = None
    quantity: float = Field(..., gt=0)
    unit_price: str
    discount_amount: Optional[str] = "0.00"
    tax_amount: Optional[str] = "0.00"


class QuoteCustomer(BaseModel):
    code: Optional[str] = None  # Si no se envía, se obtiene del usuario autenticado
    email: Optional[str] = None  # Si no se envía, se obtiene de la BD
    name: Optional[str] = None  # Si no se envía, se obtiene de la BD
    phone: Optional[str] = None  # Si no se envía, se obtiene de la BD


class QuoteDelivery(BaseModel):
    mode: Optional[Literal["pickup", "delivery"]] = "pickup"
    address_id: Optional[str] = None
    notes: Optional[str] = None
    co_tran: Optional[str] = None  # Código de transporte (001, 002, 003, etc.)

class QuoteCreate(BaseModel):
    customer: Optional[QuoteCustomer] = None  # Si no se envía, se obtiene del usuario autenticado
    channel: Optional[str] = "web_b2b"
    valid_until: Optional[str] = None  # ISO 8601 string
    currency: Optional[str] = "VES"
    payment_terms: Optional[str] = "CON"  # Código de condición de pago (CON, 3D, 5D, 7D, 10D, 12D, 14D, 15D, 16D, 20D, 21D, 30D, 360D)
    delivery: Optional[QuoteDelivery] = None
    direc: Optional[str] = None  # Dirección de entrega. Si no se envía, se usa la dirección principal (direc1) del cliente
    notes: Optional[str] = None
    items: List[QuoteItem]


class QuoteCreatedResponse(BaseModel):
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    currency: str
    total_net: str
    total_tax: str
    total_gross: str
    expires_at: Optional[str] = None
    email_sent_at: Optional[str] = None


class QuoteVerifyItemRequest(BaseModel):
    co_art: str
    cantidad: float = Field(..., gt=0)


class QuoteVerifyRequest(BaseModel):
    co_cli: str
    items: List[QuoteVerifyItemRequest]


class QuoteVerifyItemResult(BaseModel):
    co_art: str
    cantidad: float
    precio_unitario: str
    subtotal: str
    impuestos: str
    descuento: str = Field(default="0.00", description="Monto del descuento aplicado")
    stock_ok: bool = True
    nombre_articulo: Optional[str] = None


class QuoteVerifyTotals(BaseModel):
    bruto: str
    impuestos: str
    neto: str


class QuoteVerifyResponse(BaseModel):
    valido: bool
    co_cli: str
    items_verificados: List[QuoteVerifyItemResult] = []
    totales: QuoteVerifyTotals
    expires_at: Optional[str] = None


class QuoteListItem(BaseModel):
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    created_at: str
    expires_at: Optional[str] = None
    total_gross: str
    currency: str
    items_count: int
    email_sent_at: Optional[str] = None


class Pagination(BaseModel):
    page: int
    page_size: int
    total_pages: int
    total_items: int


class QuoteListResponse(BaseModel):
    results: List[QuoteListItem]
    pagination: Pagination


class QuoteDetailItem(BaseModel):
    line_number: int
    product_code: str
    product_name: Optional[str] = None
    quantity: str
    unit_price: str
    discount_amount: str
    tax_amount: str
    line_total: str


class QuoteHistoryEvent(BaseModel):
    timestamp: str
    event: str
    detail: Optional[str] = None


class QuoteTotals(BaseModel):
    total_net: str
    total_tax: str
    total_discount: Optional[str] = "0.00"
    total_gross: str


class QuoteDetailResponse(BaseModel):
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    created_at: str
    expires_at: Optional[str] = None
    currency: str
    payment_terms: Optional[str] = None
    delivery: Optional[dict] = None
    totals: QuoteTotals
    items: List[QuoteDetailItem]
    history: List[QuoteHistoryEvent] = []


class QuoteStatus(BaseModel):
    code: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    label: str
    description: str


# ============================================================================
# Cart Validation Schemas (for /api/cotizaciones/verificar)
# ============================================================================

class CartItemRequest(BaseModel):
    """
    Item mínimo que el frontend debe enviar para validación.
    Solo se acepta co_art y cantidad. Todos los demás campos se ignoran.
    """
    co_art: str = Field(..., description="Código del artículo")
    cantidad: float = Field(..., gt=0, description="Cantidad deseada")


class CartValidationRequest(BaseModel):
    """
    Payload que envía el frontend para validar un carrito.
    No requiere co_cli ya que se obtiene del usuario autenticado.
    """
    items: List[CartItemRequest] = Field(..., description="Lista de artículos a validar")


class CartValidationItemResult(BaseModel):
    """
    Resultado de validación para un artículo individual.
    Contiene la información autoritativa calculada por el backend.
    """
    co_art: str = Field(..., description="Código del artículo")
    descripcion: Optional[str] = Field(None, description="Descripción real del artículo desde la BD")
    cantidad: float = Field(..., description="Cantidad solicitada")
    precio_unitario_real: str = Field(..., description="Precio unitario real calculado por el backend")
    subtotal: str = Field(..., description="Subtotal (precio_unitario_real * cantidad)")
    impuestos: str = Field(..., description="Impuestos calculados")
    descuento: str = Field(default="0.00", description="Monto del descuento aplicado a este artículo")
    stock_ok: bool = Field(..., description="True si hay stock suficiente, False en caso contrario")
    error: Optional[str] = Field(None, description="Mensaje de error si la validación falló")


class CartValidationTotals(BaseModel):
    """
    Totales calculados para todo el carrito.
    """
    bruto: str = Field(..., description="Total bruto (suma de subtotales)")
    impuestos: str = Field(..., description="Total de impuestos")
    descuentos: str = Field(default="0.00", description="Total de descuentos aplicados")
    neto: str = Field(..., description="Total neto (bruto + impuestos - descuentos)")


class CartValidationResponse(BaseModel):
    """
    Respuesta autoritativa del backend con la validación completa del carrito.
    Este es el único objeto en el que el frontend debe confiar.
    """
    valido: bool = Field(..., description="True si todos los artículos son válidos, False si hay errores")
    items_verificados: List[CartValidationItemResult] = Field(..., description="Lista de artículos verificados")
    totales: CartValidationTotals = Field(..., description="Totales calculados")


