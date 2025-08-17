from pydantic import BaseModel, Field
from typing import Optional

class ShippingZoneBase(BaseModel):
    id: str = Field(..., description="Unique identifier for the zone (e.g., 'caracas').")
    name: str = Field(..., description="Display name for the shipping zone (e.g., 'Caracas').")
    price: float = Field(..., gt=0, description="Shipping cost for this zone.")
    delivery_days: Optional[str] = Field(None, description="Estimated delivery time in days (e.g., '1-2').")

class ShippingZoneCreate(ShippingZoneBase):
    pass

class ShippingZoneUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Display name for the shipping zone.")
    price: Optional[float] = Field(None, gt=0, description="Shipping cost for this zone.")
    delivery_days: Optional[str] = Field(None, description="Estimated delivery time in days.")

class ShippingZoneResponse(ShippingZoneBase):
    
    class Config:
        from_attributes = True
