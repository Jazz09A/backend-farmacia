from typing import Literal

from pydantic import BaseModel, Field


class QuoteItem(BaseModel):
    line_number: int = Field(..., ge=1)
    product_code: str = Field(..., description="Código del artículo (co_art)")
    product_name: str | None = Field(None, description="Opcional - Se obtiene de la BD si no se envía")
    quantity: float = Field(..., gt=0, description="Cantidad a cotizar")
    unit_price: str | None = Field(None, description="Opcional - Se obtiene de la BD si no se envía")
    discount_amount: str | None = Field("0.00", description="Opcional - Se calcula automáticamente si no se envía")
    tax_amount: str | None = Field("0.00", description="Opcional - Se calcula automáticamente si no se envía")


class QuoteCustomer(BaseModel):
    code: str | None = None  # Si no se envía, se obtiene del usuario autenticado
    email: str | None = None  # Si no se envía, se obtiene de la BD
    name: str | None = None  # Si no se envía, se obtiene de la BD
    phone: str | None = None  # Si no se envía, se obtiene de la BD


class QuoteDelivery(BaseModel):
    mode: Literal["pickup", "delivery"] | None = "pickup"
    address_id: str | None = None
    notes: str | None = None
    co_tran: str | None = None  # Código de transporte (001, 002, 003, etc.)

class QuoteCreate(BaseModel):
    customer: QuoteCustomer | None = None  # Si no se envía, se obtiene del usuario autenticado
    channel: str | None = "web_b2b"
    valid_until: str | None = None  # ISO 8601 string
    currency: str | None = "VES"
    payment_terms: str | None = "CON"  # Código de condición de pago (CON, 3D, 5D, 7D, 10D, 12D, 14D, 15D, 16D, 20D, 21D, 30D, 360D)
    delivery: QuoteDelivery | None = None
    direc: str | None = None  # Dirección de entrega. Si no se envía, se usa la dirección principal (direc1) del cliente
    notes: str | None = None
    items: list[QuoteItem]


class QuoteCreatedResponse(BaseModel):
    success: bool = Field(default=True, description="Indica si la operación fue exitosa")
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    currency: str
    total_net: str
    total_tax: str
    total_gross: str
    expires_at: str | None = None
    email_sent_at: str | None = None
    items_data: list[dict] | None = Field(default=None, description="Datos de los items obtenidos de la BD para el email")


class QuoteVerifyItemRequest(BaseModel):
    co_art: str
    cantidad: float = Field(..., gt=0)


class QuoteVerifyRequest(BaseModel):
    co_cli: str
    items: list[QuoteVerifyItemRequest]


class QuoteVerifyItemResult(BaseModel):
    co_art: str
    cantidad: float
    precio_unitario: str
    subtotal: str
    impuestos: str
    descuento: str = Field(default="0.00", description="Monto del descuento aplicado")
    stock_ok: bool = True
    nombre_articulo: str | None = None


class QuoteVerifyTotals(BaseModel):
    bruto: str
    impuestos: str
    neto: str


class QuoteVerifyResponse(BaseModel):
    success: bool = Field(default=True, description="Indica si la verificación fue exitosa")
    valido: bool
    co_cli: str
    items_verificados: list[QuoteVerifyItemResult] = []
    totales: QuoteVerifyTotals
    expires_at: str | None = None


class QuoteListItem(BaseModel):
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    created_at: str
    expires_at: str | None = None
    total_gross: str
    currency: str
    items_count: int
    email_sent_at: str | None = None


class Pagination(BaseModel):
    page: int
    page_size: int
    total_pages: int
    total_items: int


class QuoteListResponse(BaseModel):
    success: bool = Field(default=True, description="Indica si la consulta fue exitosa")
    results: list[QuoteListItem]
    pagination: Pagination


class QuoteDetailItem(BaseModel):
    line_number: int
    product_code: str
    product_name: str | None = None
    quantity: str
    unit_price: str
    discount_amount: str
    tax_amount: str
    line_total: str


class QuoteHistoryEvent(BaseModel):
    timestamp: str
    event: str
    detail: str | None = None


class QuoteTotals(BaseModel):
    total_net: str
    total_tax: str
    total_discount: str | None = "0.00"
    total_gross: str


class QuoteDetailResponse(BaseModel):
    success: bool = Field(default=True, description="Indica si la consulta fue exitosa")
    quote_id: str
    profit_plus_id: str
    status: Literal["pending", "accepted", "expired", "cancelled", "converted"]
    created_at: str
    expires_at: str | None = None
    currency: str
    payment_terms: str | None = None
    delivery: dict | None = None
    totals: QuoteTotals
    items: list[QuoteDetailItem]
    history: list[QuoteHistoryEvent] = []


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
    items: list[CartItemRequest] = Field(..., description="Lista de artículos a validar")


class CartValidationItemResult(BaseModel):
    """
    Resultado de validación para un artículo individual.
    Contiene la información autoritativa calculada por el backend.
    """
    co_art: str = Field(..., description="Código del artículo")
    descripcion: str | None = Field(None, description="Descripción real del artículo desde la BD")
    cantidad: float = Field(..., description="Cantidad solicitada")
    precio_unitario_real: str = Field(..., description="Precio unitario real calculado por el backend")
    subtotal: str = Field(..., description="Subtotal (precio_unitario_real * cantidad)")
    impuestos: str = Field(..., description="Impuestos calculados")
    descuento: str = Field(default="0.00", description="Monto del descuento aplicado a este artículo")
    descuento_info: dict | None = Field(None, description="Información del descuento aplicado (co_desc, porcentaje, disponibles, limite_total)")
    stock_ok: bool = Field(..., description="True si hay stock suficiente, False en caso contrario")
    error: str | None = Field(None, description="Mensaje de error si la validación falló")


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
    success: bool = Field(default=True, description="Indica si la validación se completó exitosamente")
    valido: bool = Field(..., description="True si todos los artículos son válidos, False si hay errores")
    items_verificados: list[CartValidationItemResult] = Field(..., description="Lista de artículos verificados")
    totales: CartValidationTotals = Field(..., description="Totales calculados")


