from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.product import ProductSummary


class CartItemCreate(BaseModel):
    """Schema for adding a new item to the cart."""
    product_id: str = Field(..., description="The ID of the product to add.")
    quantity: int = Field(1, gt=0, description="Number of items to add.")
    selected_presentation: Optional[str] = Field(None, description="The selected product presentation, if applicable.")


class CartItemUpdate(BaseModel):
    """Schema for updating the quantity of an item in the cart."""
    quantity: int = Field(..., gt=0, description="The new quantity for the item.")


class CartItemResponse(BaseModel):
    """Schema for representing a single item within the cart in API responses."""
    id: str = Field(..., description="Unique identifier for the cart item.")
    quantity: int = Field(..., description="Quantity of the product in the cart.")
    selected_presentation: Optional[str] = Field(None, description="The selected product presentation.")
    product: ProductSummary = Field(..., description="Detailed information about the product.")
    subtotal_ves: float = Field(..., description="Calculated subtotal for the item in VED.")
    subtotal_ref: float = Field(..., description="Calculated subtotal for the item in USD.")
    created_at: datetime = Field(..., description="Timestamp when the item was first added.")
    updated_at: datetime = Field(..., description="Timestamp of the last item update.")

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    """Schema for representing the user's entire shopping cart."""
    items: List[CartItemResponse] = Field(..., description="A list of all items in the cart.")
    total_items: int = Field(..., description="The total number of individual items in the cart.")
    total_unique_items: int = Field(..., description="The number of unique products in the cart.")
    total_ves: float = Field(..., description="The grand total price for all items in VED.")
    total_ref: float = Field(..., description="The grand total price for all items in USD.")

    class Config:
        from_attributes = True
