from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.product import ProductSummary
from app.schemas.promotion import QuantityDiscountResponse


class CartItemCreate(BaseModel):
    """Schema for adding a new item to the cart."""

    product_id: str = Field(..., description="The ID of the product to add.")
    quantity: int = Field(1, gt=0, description="Number of items to add.")
    selected_presentation: str | None = Field(None, description="The selected product presentation, if applicable.")


class CartItemUpdate(BaseModel):
    """Schema for updating the quantity of an item in the cart."""

    quantity: int = Field(..., gt=0, description="The new quantity for the item.")


class CartItemResponse(BaseModel):
    """Schema for representing a single item within the cart in API responses (sistema unificado USD)."""

    id: str = Field(..., description="Unique identifier for the cart item.")
    quantity: int = Field(..., description="Quantity of the product in the cart.")
    selected_presentation: str | None = Field(None, description="The selected product presentation.")
    product: ProductSummary = Field(..., description="Detailed information about the product.")
    subtotal: Decimal = Field(..., description="Calculated subtotal for the item in USD.")
    created_at: datetime = Field(..., description="Timestamp when the item was first added.")
    updated_at: datetime = Field(..., description="Timestamp of the last item update.")

    class Config:
        from_attributes = True


class CartDiscountsInfo(BaseModel):
    """Schema for discount information in cart responses."""

    quantity_discount: QuantityDiscountResponse | None = Field(None, description="Descuento por cantidad aplicado.")
    quantity_discount_amount: Decimal = Field(Decimal("0.00"), description="Monto del descuento por cantidad en USD.")
    flash_discounts: dict[str, Decimal] = Field(
        default_factory=dict, description="Descuentos flash por producto en USD."
    )
    flash_discount_total: Decimal = Field(Decimal("0.00"), description="Total de descuentos flash en USD.")
    total_discount: Decimal = Field(Decimal("0.00"), description="Total de todos los descuentos en USD.")
    subtotal_after_discounts: Decimal = Field(
        Decimal("0.00"), description="Subtotal después de aplicar descuentos en USD."
    )

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    """Schema for representing the user's entire shopping cart (sistema unificado USD)."""

    items: list[CartItemResponse] = Field(..., description="A list of all items in the cart.")
    total_items: int = Field(..., description="The total number of individual items in the cart.")
    total_unique_items: int = Field(..., description="The number of unique products in the cart.")
    total: Decimal = Field(..., description="The grand total price for all items in USD.")
    discounts: CartDiscountsInfo = Field(..., description="Información completa de descuentos aplicados.")

    class Config:
        from_attributes = True
